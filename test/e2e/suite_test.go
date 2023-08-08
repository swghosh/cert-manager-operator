package e2e

import (
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	"github.com/openshift/cert-manager-operator/pkg/controller/deployment"
	certmanoperatorclient "github.com/openshift/cert-manager-operator/pkg/operator/clientset/versioned"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"sigs.k8s.io/controller-runtime/pkg/client/config"
)

var (
	cfg          *rest.Config
	k8sClientSet *kubernetes.Clientset

	certmanageroperatorclient *certmanoperatorclient.Clientset
)

func TestAll(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Cert Manager Suite")
}

var _ = BeforeSuite(func() {
	var err error
	cfg, err = config.GetConfig()
	Expect(err).NotTo(HaveOccurred())

	k8sClientSet, err = kubernetes.NewForConfig(cfg)
	Expect(err).NotTo(HaveOccurred())

	certmanageroperatorclient, err = certmanoperatorclient.NewForConfig(cfg)
	Expect(err).NotTo(HaveOccurred())
	Expect(certmanageroperatorclient).NotTo(BeNil())

	err = waitForValidOperatorStatusCondition(certmanageroperatorclient,
		[]string{deployment.CertManagerControllerDeploymentControllerName,
			deployment.CertManagerWebhookDeploymentControllerName,
			deployment.CertManagerCAInjectorDeploymentControllerName})
	Expect(err).NotTo(HaveOccurred(), "operator is expected to be available")
})
