package deployment

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	networkingv1 "k8s.io/api/networking/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/client-go/kubernetes/fake"
	"k8s.io/utils/clock"

	"github.com/openshift/library-go/pkg/operator/events"
)

func newTestController() (*CertManagerNetworkPolicyUserDefinedController, events.InMemoryRecorder) {
	recorder := events.NewInMemoryRecorder("test", clock.RealClock{})
	c := &CertManagerNetworkPolicyUserDefinedController{
		kubeClient:    fake.NewSimpleClientset(),
		eventRecorder: recorder.WithComponentSuffix("cert-manager-networkpolicy-user-defined"),
	}
	return c, recorder
}

func newTestNetworkPolicy(name string, port int) *networkingv1.NetworkPolicy {
	proto := corev1.ProtocolTCP
	return &networkingv1.NetworkPolicy{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: certManagerNamespace,
			Labels: map[string]string{
				networkPolicyOwnerLabel: "cert-manager",
			},
		},
		Spec: networkingv1.NetworkPolicySpec{
			PodSelector: metav1.LabelSelector{
				MatchLabels: map[string]string{"app": "cert-manager"},
			},
			PolicyTypes: []networkingv1.PolicyType{
				networkingv1.PolicyTypeEgress,
			},
			Egress: []networkingv1.NetworkPolicyEgressRule{
				{
					Ports: []networkingv1.NetworkPolicyPort{
						{
							Port:     &intstr.IntOrString{Type: intstr.Int, IntVal: int32(port)},
							Protocol: &proto,
						},
					},
				},
			},
		},
	}
}

func TestCreateOrUpdateNetworkPolicy_Create(t *testing.T) {
	c, recorder := newTestController()
	ctx := context.Background()

	policy := newTestNetworkPolicy("cert-manager-user-test", 443)
	changed, err := c.createOrUpdateNetworkPolicy(ctx, policy)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !changed {
		t.Fatal("expected changed=true for new policy creation")
	}

	evts := recorder.Events()
	if len(evts) != 1 {
		t.Fatalf("expected 1 event, got %d", len(evts))
	}
	if evts[0].Reason != "NetworkPolicyCreated" {
		t.Errorf("expected reason NetworkPolicyCreated, got %s", evts[0].Reason)
	}
}

func TestCreateOrUpdateNetworkPolicy_NoOpUpdate(t *testing.T) {
	c, recorder := newTestController()
	ctx := context.Background()

	policy := newTestNetworkPolicy("cert-manager-user-test", 443)

	_, err := c.kubeClient.NetworkingV1().NetworkPolicies(certManagerNamespace).Create(ctx, policy, metav1.CreateOptions{})
	if err != nil {
		t.Fatalf("setup: unexpected error: %v", err)
	}

	changed, err := c.createOrUpdateNetworkPolicy(ctx, policy)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if changed {
		t.Fatal("expected changed=false when spec and labels are identical")
	}

	evts := recorder.Events()
	if len(evts) != 0 {
		t.Fatalf("expected 0 events for no-op update, got %d", len(evts))
	}
}

func TestCreateOrUpdateNetworkPolicy_UpdateOnSpecChange(t *testing.T) {
	c, recorder := newTestController()
	ctx := context.Background()

	original := newTestNetworkPolicy("cert-manager-user-test", 443)
	_, err := c.kubeClient.NetworkingV1().NetworkPolicies(certManagerNamespace).Create(ctx, original, metav1.CreateOptions{})
	if err != nil {
		t.Fatalf("setup: unexpected error: %v", err)
	}

	updated := newTestNetworkPolicy("cert-manager-user-test", 8443)
	changed, err := c.createOrUpdateNetworkPolicy(ctx, updated)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !changed {
		t.Fatal("expected changed=true when spec differs")
	}

	evts := recorder.Events()
	if len(evts) != 1 {
		t.Fatalf("expected 1 event, got %d", len(evts))
	}
	if evts[0].Reason != "NetworkPolicyUpdated" {
		t.Errorf("expected reason NetworkPolicyUpdated, got %s", evts[0].Reason)
	}
}
