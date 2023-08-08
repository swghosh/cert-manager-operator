package e2e

import (
	"context"
	"fmt"
	"sync"
	"time"

	opv1 "github.com/openshift/api/operator/v1"
	"github.com/openshift/cert-manager-operator/api/operator/v1alpha1"
	"github.com/openshift/cert-manager-operator/pkg/controller/deployment"
	certmanoperatorclient "github.com/openshift/cert-manager-operator/pkg/operator/clientset/versioned"
	"github.com/openshift/cert-manager-operator/pkg/operator/operatorclient"

	v1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/sets"
	"k8s.io/apimachinery/pkg/util/wait"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/util/retry"
)

func waitForValidOperatorStatusCondition(client *certmanoperatorclient.Clientset, controllerNames []string) error {

	var wg sync.WaitGroup
	errs := make([]error, len(controllerNames))
	for index := range controllerNames {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			err := wait.PollImmediate(time.Second*1, time.Minute*5, func() (done bool, err error) {
				operator, err := client.OperatorV1alpha1().CertManagers().Get(context.TODO(), "cluster", v1.GetOptions{})
				if err != nil {
					return false, err
				}

				if operator.DeletionTimestamp != nil {
					return false, nil
				}

				flag := false
				for _, cond := range operator.Status.Conditions {
					if cond.Type == controllerNames[index]+"Available" {
						flag = cond.Status == opv1.ConditionTrue
					}

					if cond.Type == controllerNames[index]+"Degraded" {
						flag = cond.Status == opv1.ConditionFalse
					}

					if cond.Type == controllerNames[index]+"Progressing" {
						flag = cond.Status == opv1.ConditionFalse
					}
				}

				return flag, nil
			})
			errs[index] = err
		}(index)
	}
	wg.Wait()

	for _, err := range errs {
		if err != nil {
			return err
		}
	}

	return nil
}

func waitForInvalidOperatorStatusCondition(client *certmanoperatorclient.Clientset, controllerNames []string) error {

	var wg sync.WaitGroup
	errs := make([]error, len(controllerNames))
	for index := range controllerNames {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			err := wait.PollImmediate(time.Second*1, time.Minute*5, func() (done bool, err error) {
				operator, err := client.OperatorV1alpha1().CertManagers().Get(context.TODO(), "cluster", v1.GetOptions{})
				if err != nil {
					return false, err
				}

				if operator.DeletionTimestamp != nil {
					return false, nil
				}

				flag := false
				for _, cond := range operator.Status.Conditions {
					if cond.Type == controllerNames[index]+"Degraded" {
						flag = cond.Status == opv1.ConditionTrue
					}
				}

				return flag, nil
			})
			errs[index] = err
		}(index)
	}
	wg.Wait()

	for _, err := range errs {
		if err != nil {
			return err
		}
	}
	return nil
}

func removeOverrides(client *certmanoperatorclient.Clientset) error {
	return retry.RetryOnConflict(retry.DefaultRetry, func() error {
		operator, err := client.OperatorV1alpha1().CertManagers().Get(context.TODO(), "cluster", v1.GetOptions{})
		if err != nil {
			return err
		}

		updatedOperator := operator.DeepCopy()

		hasOverride := false
		if updatedOperator.Spec.ControllerConfig != nil {
			updatedOperator.Spec.ControllerConfig = nil
			hasOverride = true
		}
		if updatedOperator.Spec.WebhookConfig != nil {
			updatedOperator.Spec.WebhookConfig = nil
			hasOverride = true
		}
		if updatedOperator.Spec.CAInjectorConfig != nil {
			updatedOperator.Spec.CAInjectorConfig = nil
			hasOverride = true
		}

		if !hasOverride {
			return nil
		}

		_, err = client.OperatorV1alpha1().CertManagers().Update(context.TODO(), updatedOperator, v1.UpdateOptions{})
		return err
	})

}

func addOverrideArgs(client *certmanoperatorclient.Clientset, deploymentName string, args []string) error {
	return retry.RetryOnConflict(retry.DefaultRetry, func() error {
		operator, err := client.OperatorV1alpha1().CertManagers().Get(context.TODO(), "cluster", v1.GetOptions{})
		if err != nil {
			return err
		}

		updatedOperator := operator.DeepCopy()

		switch deploymentName {
		case deployment.CertmanagerControllerDeployment:
			updatedOperator.Spec.ControllerConfig = &v1alpha1.DeploymentConfig{
				OverrideArgs: args,
			}
		case deployment.CertmanagerWebhookDeployment:
			updatedOperator.Spec.WebhookConfig = &v1alpha1.DeploymentConfig{
				OverrideArgs: args,
			}
		case deployment.CertmanagerCAinjectorDeployment:
			updatedOperator.Spec.CAInjectorConfig = &v1alpha1.DeploymentConfig{
				OverrideArgs: args,
			}
		default:
			return fmt.Errorf("unsupported deployment name: %s", deploymentName)
		}

		_, err = client.OperatorV1alpha1().CertManagers().Update(context.TODO(), updatedOperator, v1.UpdateOptions{})
		return err
	})
}

func waitForDeploymentArgs(k8sclient *kubernetes.Clientset, deploymentName string, args []string, added bool) error {

	return wait.PollImmediate(time.Second*1, time.Minute*5, func() (done bool, err error) {
		controllerDeployment, err := k8sclient.AppsV1().Deployments(operatorclient.TargetNamespace).Get(context.TODO(), deploymentName, v1.GetOptions{})
		if err != nil {
			return false, err
		}

		if len(controllerDeployment.Spec.Template.Spec.Containers) == 0 {
			return false, fmt.Errorf("%s deployment spec does not have container information", deploymentName)
		}

		containerArgsSet := sets.New[string](controllerDeployment.Spec.Template.Spec.Containers[0].Args...)

		if added {
			if !containerArgsSet.HasAll(args...) {
				return false, nil
			}
		} else {
			if containerArgsSet.HasAll(args...) {
				return false, nil
			}
		}

		return true, nil
	})
}
