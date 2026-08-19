package deployment

import (
	"testing"

	v1 "github.com/openshift/api/operator/v1"
	appsv1 "k8s.io/api/apps/v1"
	"k8s.io/client-go/tools/cache"

	"github.com/openshift/cert-manager-operator/api/operator/v1alpha1"
	certmanagerinformer "github.com/openshift/cert-manager-operator/pkg/operator/informers/externalversions/operator/v1alpha1"
	certmanagerlister "github.com/openshift/cert-manager-operator/pkg/operator/listers/operator/v1alpha1"
)

type fakeCertManagerInformer struct {
	indexer cache.Indexer
}

func (f *fakeCertManagerInformer) Informer() cache.SharedIndexInformer {
	return nil
}

func (f *fakeCertManagerInformer) Lister() certmanagerlister.CertManagerLister {
	return certmanagerlister.NewCertManagerLister(f.indexer)
}

var _ certmanagerinformer.CertManagerInformer = &fakeCertManagerInformer{}

func newFakeCertManagerInformer(certmanager *v1alpha1.CertManager) certmanagerinformer.CertManagerInformer {
	indexer := cache.NewIndexer(cache.MetaNamespaceKeyFunc, cache.Indexers{})
	indexer.Add(certmanager)
	return &fakeCertManagerInformer{indexer: indexer}
}

func TestWithPodLabelsValidateHook(t *testing.T) {
	tests := []struct {
		name           string
		deploymentName string
		certmanager    *v1alpha1.CertManager
		wantErr        bool
	}{
		{
			name:           "webhook config set without controller config should not panic",
			deploymentName: certmanagerWebhookDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{
					WebhookConfig: &v1alpha1.DeploymentConfig{
						OverrideArgs: []string{"--v=4"},
					},
				},
			},
		},
		{
			name:           "cainjector config set without controller config should not panic",
			deploymentName: certmanagerCAinjectorDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{
					CAInjectorConfig: &v1alpha1.DeploymentConfig{
						OverrideArgs: []string{"--v=2"},
					},
				},
			},
		},
		{
			name:           "webhook with unsupported label returns error",
			deploymentName: certmanagerWebhookDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{
					WebhookConfig: &v1alpha1.DeploymentConfig{
						OverrideLabels: map[string]string{
							"unsupported-label": "value",
						},
					},
				},
			},
			wantErr: true,
		},
		{
			name:           "cainjector with unsupported label returns error",
			deploymentName: certmanagerCAinjectorDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{
					CAInjectorConfig: &v1alpha1.DeploymentConfig{
						OverrideLabels: map[string]string{
							"unsupported-label": "value",
						},
					},
				},
			},
			wantErr: true,
		},
		{
			name:           "controller with supported label succeeds",
			deploymentName: certmanagerControllerDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{
					ControllerConfig: &v1alpha1.DeploymentConfig{
						OverrideLabels: map[string]string{
							"azure.workload.identity/use": "true",
						},
					},
				},
			},
		},
		{
			name:           "nil configs should not panic for webhook",
			deploymentName: certmanagerWebhookDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{},
			},
		},
		{
			name:           "nil configs should not panic for cainjector",
			deploymentName: certmanagerCAinjectorDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{},
			},
		},
		{
			name:           "nil configs should not panic for controller",
			deploymentName: certmanagerControllerDeployment,
			certmanager: &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{},
			},
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			tc.certmanager.Name = "cluster"
			informer := newFakeCertManagerInformer(tc.certmanager)
			hook := withPodLabelsValidateHook(informer, tc.deploymentName)
			err := hook(&v1.OperatorSpec{}, &appsv1.Deployment{})
			if tc.wantErr && err == nil {
				t.Errorf("expected error but got nil")
			}
			if !tc.wantErr && err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}
