package deployment

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	networkingv1 "k8s.io/api/networking/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	kubefake "k8s.io/client-go/kubernetes/fake"

	"github.com/openshift/library-go/pkg/operator/events"
	"github.com/openshift/library-go/pkg/operator/resource/resourceapply"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"k8s.io/utils/clock"

	"github.com/openshift/cert-manager-operator/api/operator/v1alpha1"
)

func newTestController(existingObjects ...runtime.Object) *CertManagerNetworkPolicyUserDefinedController {
	return &CertManagerNetworkPolicyUserDefinedController{
		kubeClient:    kubefake.NewSimpleClientset(existingObjects...),
		eventRecorder: events.NewInMemoryRecorder("test", clock.RealClock{}),
		resourceCache: resourceapply.NewResourceCache(),
	}
}

func TestReconcileUserNetworkPolicies_CreatesNewPolicy(t *testing.T) {
	c := newTestController()
	certManager := &v1alpha1.CertManager{
		Spec: v1alpha1.CertManagerSpec{
			NetworkPolicies: []v1alpha1.NetworkPolicy{
				{
					Name:          "allow-egress-dns",
					ComponentName: v1alpha1.CoreController,
					Egress: []networkingv1.NetworkPolicyEgressRule{
						{
							Ports: []networkingv1.NetworkPolicyPort{
								{Protocol: protocolPtr(corev1.ProtocolUDP)},
							},
						},
					},
				},
			},
		},
	}

	err := c.reconcileUserNetworkPolicies(context.Background(), certManager)
	require.NoError(t, err)

	np, err := c.kubeClient.NetworkingV1().NetworkPolicies(certManagerNamespace).Get(
		context.Background(), "cert-manager-user-allow-egress-dns", metav1.GetOptions{})
	require.NoError(t, err)
	assert.Equal(t, "cert-manager", np.Labels[networkPolicyOwnerLabel])
	assert.Equal(t, networkingv1.PolicyTypeEgress, np.Spec.PolicyTypes[0])
	assert.Equal(t, "cert-manager", np.Spec.PodSelector.MatchLabels["app"])
}

func TestReconcileUserNetworkPolicies_IdempotentNoUpdate(t *testing.T) {
	c := newTestController()
	certManager := &v1alpha1.CertManager{
		Spec: v1alpha1.CertManagerSpec{
			NetworkPolicies: []v1alpha1.NetworkPolicy{
				{
					Name:          "allow-egress-dns",
					ComponentName: v1alpha1.CoreController,
				},
			},
		},
	}

	err := c.reconcileUserNetworkPolicies(context.Background(), certManager)
	require.NoError(t, err)

	recorder := c.eventRecorder.(events.InMemoryRecorder)
	initialEvents := len(recorder.Events())

	err = c.reconcileUserNetworkPolicies(context.Background(), certManager)
	require.NoError(t, err)

	assert.Equal(t, initialEvents, len(recorder.Events()),
		"second reconcile should not generate new events because spec is unchanged")
}

func TestReconcileUserNetworkPolicies_UpdatesChangedSpec(t *testing.T) {
	c := newTestController()
	certManager := &v1alpha1.CertManager{
		Spec: v1alpha1.CertManagerSpec{
			NetworkPolicies: []v1alpha1.NetworkPolicy{
				{
					Name:          "allow-egress",
					ComponentName: v1alpha1.Webhook,
				},
			},
		},
	}

	err := c.reconcileUserNetworkPolicies(context.Background(), certManager)
	require.NoError(t, err)

	certManager.Spec.NetworkPolicies[0].Egress = []networkingv1.NetworkPolicyEgressRule{
		{
			Ports: []networkingv1.NetworkPolicyPort{
				{Protocol: protocolPtr(corev1.ProtocolTCP)},
			},
		},
	}

	err = c.reconcileUserNetworkPolicies(context.Background(), certManager)
	require.NoError(t, err)

	np, err := c.kubeClient.NetworkingV1().NetworkPolicies(certManagerNamespace).Get(
		context.Background(), "cert-manager-user-allow-egress", metav1.GetOptions{})
	require.NoError(t, err)
	require.Len(t, np.Spec.Egress, 1)
	require.Len(t, np.Spec.Egress[0].Ports, 1)
	assert.Equal(t, corev1.ProtocolTCP, *np.Spec.Egress[0].Ports[0].Protocol)
}

func TestReconcileUserNetworkPolicies_MultiplePolicies(t *testing.T) {
	c := newTestController()
	certManager := &v1alpha1.CertManager{
		Spec: v1alpha1.CertManagerSpec{
			NetworkPolicies: []v1alpha1.NetworkPolicy{
				{Name: "policy-a", ComponentName: v1alpha1.CoreController},
				{Name: "policy-b", ComponentName: v1alpha1.Webhook},
				{Name: "policy-c", ComponentName: v1alpha1.CAInjector},
			},
		},
	}

	err := c.reconcileUserNetworkPolicies(context.Background(), certManager)
	require.NoError(t, err)

	npList, err := c.kubeClient.NetworkingV1().NetworkPolicies(certManagerNamespace).List(
		context.Background(), metav1.ListOptions{})
	require.NoError(t, err)
	assert.Len(t, npList.Items, 3)
}

func TestCreateUserNetworkPolicy_Shape(t *testing.T) {
	c := newTestController()

	tests := []struct {
		name             string
		policy           v1alpha1.NetworkPolicy
		expectedName     string
		expectedSelector map[string]string
	}{
		{
			name:             "CoreController component",
			policy:           v1alpha1.NetworkPolicy{Name: "test", ComponentName: v1alpha1.CoreController},
			expectedName:     "cert-manager-user-test",
			expectedSelector: map[string]string{"app": "cert-manager"},
		},
		{
			name:             "Webhook component",
			policy:           v1alpha1.NetworkPolicy{Name: "wh-policy", ComponentName: v1alpha1.Webhook},
			expectedName:     "cert-manager-user-wh-policy",
			expectedSelector: map[string]string{"app": "webhook"},
		},
		{
			name:             "CAInjector component",
			policy:           v1alpha1.NetworkPolicy{Name: "ca-pol", ComponentName: v1alpha1.CAInjector},
			expectedName:     "cert-manager-user-ca-pol",
			expectedSelector: map[string]string{"app": "cainjector"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			np := c.createUserNetworkPolicy(tc.policy)
			assert.Equal(t, tc.expectedName, np.Name)
			assert.Equal(t, certManagerNamespace, np.Namespace)
			assert.Equal(t, "cert-manager", np.Labels[networkPolicyOwnerLabel])
			assert.Equal(t, tc.expectedSelector, np.Spec.PodSelector.MatchLabels)
			require.Len(t, np.Spec.PolicyTypes, 1)
			assert.Equal(t, networkingv1.PolicyTypeEgress, np.Spec.PolicyTypes[0])
		})
	}
}

func TestValidateNetworkPolicyConfig(t *testing.T) {
	c := newTestController()

	tests := []struct {
		name      string
		policies  []v1alpha1.NetworkPolicy
		expectErr bool
	}{
		{
			name:      "valid policy",
			policies:  []v1alpha1.NetworkPolicy{{Name: "test", ComponentName: v1alpha1.CoreController}},
			expectErr: false,
		},
		{
			name:      "empty name",
			policies:  []v1alpha1.NetworkPolicy{{Name: "", ComponentName: v1alpha1.CoreController}},
			expectErr: true,
		},
		{
			name:      "invalid component name",
			policies:  []v1alpha1.NetworkPolicy{{Name: "test", ComponentName: "InvalidComponent"}},
			expectErr: true,
		},
		{
			name: "multiple valid policies",
			policies: []v1alpha1.NetworkPolicy{
				{Name: "a", ComponentName: v1alpha1.CoreController},
				{Name: "b", ComponentName: v1alpha1.Webhook},
			},
			expectErr: false,
		},
		{
			name:      "empty policies list",
			policies:  []v1alpha1.NetworkPolicy{},
			expectErr: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			cm := &v1alpha1.CertManager{
				Spec: v1alpha1.CertManagerSpec{NetworkPolicies: tc.policies},
			}
			err := c.validateNetworkPolicyConfig(cm)
			if tc.expectErr {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

func protocolPtr(p corev1.Protocol) *corev1.Protocol {
	return &p
}
