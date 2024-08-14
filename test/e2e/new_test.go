package e2e

import (
	"fmt"
	"testing"

	"k8s.io/client-go/kubernetes"
	"sigs.k8s.io/controller-runtime/pkg/client/config"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	gwapi "sigs.k8s.io/gateway-api/apis/v1"
)

func TestGatewayAPIPresence(t *testing.T) {
	cfg, err := config.GetConfig()
	if err != nil {
		t.Fatal(err)
	}

	k8sClientSet, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		t.Fatal(err)
	}

	d := k8sClientSet.Discovery()
	resources, err := d.ServerResourcesForGroupVersion(gwapi.GroupVersion.String())
	var GatewayAPINotAvailable = "the Gateway API CRDs do not seem to be present"
	switch {
	case apierrors.IsNotFound(err):
		t.Fatalf("gwapi not found, %q", err)
	case len(resources.APIResources) == 0:
		t.Fatalf("gwapi not found, %q", fmt.Errorf("%s (found %d APIResources in %s)", GatewayAPINotAvailable, len(resources.APIResources), gwapi.GroupVersion.String()))
	}
}
