package deployment

import (
	"testing"

	appsv1 "k8s.io/api/apps/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/client-go/tools/cache"

	v1 "github.com/openshift/api/operator/v1"

	"github.com/openshift/cert-manager-operator/api/operator/v1alpha1"
	certmanagerinformer "github.com/openshift/cert-manager-operator/pkg/operator/informers/externalversions/operator/v1alpha1"
	certmanagerlister "github.com/openshift/cert-manager-operator/pkg/operator/listers/operator/v1alpha1"
)

type fakeCertManagerInformer struct {
	lister *fakeCertManagerLister
}

func (f *fakeCertManagerInformer) Informer() cache.SharedIndexInformer {
	return nil
}

func (f *fakeCertManagerInformer) Lister() certmanagerlister.CertManagerLister {
	return f.lister
}

type fakeCertManagerLister struct {
	certmanager *v1alpha1.CertManager
}

func (f *fakeCertManagerLister) List(selector labels.Selector) (ret []*v1alpha1.CertManager, err error) {
	if f.certmanager != nil {
		return []*v1alpha1.CertManager{f.certmanager}, nil
	}
	return nil, nil
}

func (f *fakeCertManagerLister) Get(name string) (*v1alpha1.CertManager, error) {
	return f.certmanager, nil
}

func newFakeInformer(cm *v1alpha1.CertManager) certmanagerinformer.CertManagerInformer {
	return &fakeCertManagerInformer{
		lister: &fakeCertManagerLister{certmanager: cm},
	}
}

func newCertManager(controllerLabels, webhookLabels, cainjectorLabels map[string]string) *v1alpha1.CertManager {
	cm := &v1alpha1.CertManager{
		ObjectMeta: metav1.ObjectMeta{Name: "cluster"},
		Spec:       v1alpha1.CertManagerSpec{},
	}
	if controllerLabels != nil {
		cm.Spec.ControllerConfig = &v1alpha1.DeploymentConfig{OverrideLabels: controllerLabels}
	}
	if webhookLabels != nil {
		cm.Spec.WebhookConfig = &v1alpha1.DeploymentConfig{OverrideLabels: webhookLabels}
	}
	if cainjectorLabels != nil {
		cm.Spec.CAInjectorConfig = &v1alpha1.DeploymentConfig{OverrideLabels: cainjectorLabels}
	}
	return cm
}

func TestWithPodLabelsValidateHook(t *testing.T) {
	dummyOperatorSpec := &v1.OperatorSpec{}
	dummyDeployment := &appsv1.Deployment{}

	tests := map[string]struct {
		deploymentName   string
		controllerLabels map[string]string
		webhookLabels    map[string]string
		cainjectorLabels map[string]string
		wantErr          bool
	}{
		"controller with supported label should pass": {
			deploymentName:   certmanagerControllerDeployment,
			controllerLabels: map[string]string{"azure.workload.identity/use": "true"},
			wantErr:          false,
		},
		"controller with unsupported label should fail": {
			deploymentName:   certmanagerControllerDeployment,
			controllerLabels: map[string]string{"unsupported-key": "value"},
			wantErr:          true,
		},
		"controller with nil config should pass": {
			deploymentName: certmanagerControllerDeployment,
			wantErr:        false,
		},
		"webhook with nil config should pass": {
			deploymentName: certmanagerWebhookDeployment,
			wantErr:        false,
		},
		"cainjector with nil config should pass": {
			deploymentName: certmanagerCAinjectorDeployment,
			wantErr:        false,
		},
		"webhook config non-nil with controller config nil should not panic": {
			deploymentName: certmanagerWebhookDeployment,
			webhookLabels:  map[string]string{},
			wantErr:        false,
		},
		"cainjector config non-nil with controller config nil should not panic": {
			deploymentName:   certmanagerCAinjectorDeployment,
			cainjectorLabels: map[string]string{},
			wantErr:          false,
		},
		"webhook with unsupported label should fail": {
			deploymentName: certmanagerWebhookDeployment,
			webhookLabels:  map[string]string{"unsupported-key": "value"},
			wantErr:        true,
		},
		"cainjector with unsupported label should fail": {
			deploymentName:   certmanagerCAinjectorDeployment,
			cainjectorLabels: map[string]string{"unsupported-key": "value"},
			wantErr:          true,
		},
		"all configs nil should pass for controller": {
			deploymentName: certmanagerControllerDeployment,
			wantErr:        false,
		},
		"all configs nil should pass for webhook": {
			deploymentName: certmanagerWebhookDeployment,
			wantErr:        false,
		},
		"all configs nil should pass for cainjector": {
			deploymentName: certmanagerCAinjectorDeployment,
			wantErr:        false,
		},
		"webhook non-nil with empty labels and cainjector non-nil with empty labels should not panic": {
			deploymentName:   certmanagerWebhookDeployment,
			webhookLabels:    map[string]string{},
			cainjectorLabels: map[string]string{},
			wantErr:          false,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			cm := newCertManager(tc.controllerLabels, tc.webhookLabels, tc.cainjectorLabels)
			informer := newFakeInformer(cm)
			hook := withPodLabelsValidateHook(informer, tc.deploymentName)
			err := hook(dummyOperatorSpec, dummyDeployment)
			if tc.wantErr && err == nil {
				t.Errorf("expected error but got nil")
			}
			if !tc.wantErr && err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}
