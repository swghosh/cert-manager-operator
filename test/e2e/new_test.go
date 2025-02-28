//go:build e2e
// +build e2e

package e2e

import (
	"context"
	"testing"

	"github.com/openshift/cert-manager-operator/api/operator/v1alpha1"
	"github.com/openshift/cert-manager-operator/test/library"
	"github.com/stretchr/testify/require"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"sigs.k8s.io/controller-runtime/pkg/client/config"
)

func TestNewStuff(t *testing.T) {
	var dynamicClient *dynamic.DynamicClient
	var err error
	cfg, err = config.GetConfig()
	require.NoError(t, err)

	_, err = kubernetes.NewForConfig(cfg)
	require.NoError(t, err)

	dynamicClient, err = dynamic.NewForConfig(cfg)
	require.NoError(t, err)

	namespace := "istio-system"
	istioCsrName := "default"
	ctx := context.TODO()

	var istioCSRGRPCEndpoint string
	gvr := schema.GroupVersionResource{
		Group:    "operator.openshift.io",
		Version:  "v1alpha1",
		Resource: "istiocsrs",
	}

	customResource, err := dynamicClient.Resource(gvr).Namespace(namespace).Get(ctx, istioCsrName, metav1.GetOptions{})
	require.NoError(t, err)

	status, found, err := unstructured.NestedMap(customResource.Object, "status")
	if !found {
		t.Fatal("not found status")
	}

	require.NoError(t, err)

	if !library.IsEmptyString(status["istioCSRGRPCEndpoint"]) {
		istioCSRGRPCEndpoint = status["istioCSRGRPCEndpoint"].(string)
	}

	t.Logf("grpc: %s", istioCSRGRPCEndpoint)

	var istioCSRStatus v1alpha1.IstioCSRStatus
	err = runtime.DefaultUnstructuredConverter.FromUnstructured(status, &istioCSRStatus)
	require.NoError(t, err)

	t.Logf("status: %v", istioCSRStatus)
}
