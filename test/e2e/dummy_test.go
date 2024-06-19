package e2e

import (
	"os"
	"testing"

	"github.com/stretchr/testify/require"
	networkingv1 "k8s.io/api/networking/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/cli-runtime/pkg/printers"
	"k8s.io/utils/pointer"
)

func TestDummy(t *testing.T) {
	host := "python-web-service-copy.apps.sgoodwin071824.devcluster.openshift.com"
	ingress := &networkingv1.Ingress{
		TypeMeta: metav1.TypeMeta{
			APIVersion: "networking.k8s.io/v1",
			Kind:       "Ingress",
		},
		ObjectMeta: metav1.ObjectMeta{
			Name:      "python-web-copy",
			Namespace: "sandbox",
			Annotations: map[string]string{
				"cert-manager.io/issuer":                    "openssl-bootstrap-ca-issuer",
				"acme.cert-manager.io/http01-ingress-class": "openshift-default",
			},
		},
		Spec: networkingv1.IngressSpec{
			IngressClassName: pointer.String("openshift-default"),
			Rules: []networkingv1.IngressRule{
				{
					Host: host,
					IngressRuleValue: networkingv1.IngressRuleValue{
						HTTP: &networkingv1.HTTPIngressRuleValue{
							Paths: []networkingv1.HTTPIngressPath{
								{
									Path:     "/",
									PathType: (*networkingv1.PathType)(pointer.String(string(networkingv1.PathTypePrefix))),
									Backend:  networkingv1.IngressBackend{Service: &networkingv1.IngressServiceBackend{Name: "python-web", Port: networkingv1.ServiceBackendPort{Name: "http"}}},
								},
							},
						},
					},
				},
			},
			TLS: []networkingv1.IngressTLS{{
				Hosts:      []string{host},
				SecretName: "ingress-cert",
			}},
		},
	}

	newFile, err := os.Create("ingress.yaml")
	require.NoError(t, err)
	y := printers.YAMLPrinter{}
	defer newFile.Close()
	y.PrintObj(ingress, newFile)
}
