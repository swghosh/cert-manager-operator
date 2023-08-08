package e2e

import (
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"

	"github.com/openshift/cert-manager-operator/pkg/controller/deployment"
)

var _ = Describe("Overrides test", Ordered, func() {

	BeforeEach(func() {
		By("Removing any existing overrides")
		err := removeOverrides(certmanageroperatorclient)
		Expect(err).NotTo(HaveOccurred())

		By("Waiting for operator status to become available")
		err = waitForValidOperatorStatusCondition(certmanageroperatorclient,
			[]string{deployment.CertManagerControllerDeploymentControllerName,
				deployment.CertManagerWebhookDeploymentControllerName,
				deployment.CertManagerCAInjectorDeploymentControllerName})
		Expect(err).NotTo(HaveOccurred(), "Operator is expected to be available")
	})

	Context("When adding valid cert-manager controller override args", func() {

		It("should add the args to the cert-manager controller deployment", func() {

			By("Adding cert-manager controller override args to the cert-managaer operator object")
			args := []string{"--dns01-recursive-nameservers=10.10.10.10:53", "--dns01-recursive-nameservers-only", "--enable-certificate-owner-ref", "--v=3"}
			err := addOverrideArgs(certmanageroperatorclient, deployment.CertmanagerControllerDeployment, args)
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for cert-manager controller status to become available")
			err = waitForValidOperatorStatusCondition(certmanageroperatorclient, []string{deployment.CertManagerControllerDeploymentControllerName})
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for the args to be added to the cert-manager controller deployment")
			err = waitForDeploymentArgs(k8sClientSet, deployment.CertmanagerControllerDeployment, args, true)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("When adding valid cert-manager webhook override args", func() {

		It("should add the args to the cert-manager webhook deployment", func() {

			By("Adding cert-manager webhook override args to the cert-managaer operator object")
			args := []string{"--v=3"}
			err := addOverrideArgs(certmanageroperatorclient, deployment.CertmanagerWebhookDeployment, args)
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for cert-manager webhook controller status to become available")
			err = waitForValidOperatorStatusCondition(certmanageroperatorclient, []string{deployment.CertManagerWebhookDeploymentControllerName})
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for the args to be added to the cert-manager webhook deployment")
			err = waitForDeploymentArgs(k8sClientSet, deployment.CertmanagerWebhookDeployment, args, true)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("When adding valid cert-manager cainjector override args", func() {

		It("should add the args to the cert-manager cainjector deployment", func() {

			By("Adding cert-manager cainjector override args to the cert-managaer operator object")
			args := []string{"--v=3"}
			err := addOverrideArgs(certmanageroperatorclient, deployment.CertmanagerCAinjectorDeployment, args)
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for cert-manager cainjector controller status to become available")
			err = waitForValidOperatorStatusCondition(certmanageroperatorclient, []string{deployment.CertManagerCAInjectorDeploymentControllerName})
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for the args to be added to the cert-manager cainjector deployment")
			err = waitForDeploymentArgs(k8sClientSet, deployment.CertmanagerCAinjectorDeployment, args, true)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("When adding invalid cert-manager controller override args", func() {

		It("should not add the args to the cert-manager controller deployment", func() {

			By("Adding cert-manager controller override args to the cert-managaer operator object")
			args := []string{"--invalid-args=foo"}
			err := addOverrideArgs(certmanageroperatorclient, deployment.CertmanagerControllerDeployment, args)
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for cert-manager controller status to become degraded")
			err = waitForInvalidOperatorStatusCondition(certmanageroperatorclient, []string{deployment.CertManagerControllerDeploymentControllerName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking if the args are not added to the cert-manager controller deployment")
			err = waitForDeploymentArgs(k8sClientSet, deployment.CertmanagerControllerDeployment, args, false)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("When adding invalid cert-manager webhook override args", func() {

		It("should not add the args to the cert-manager webhook deployment", func() {

			By("Adding cert-manager webhook override args to the cert-managaer operator object")
			args := []string{"--dns01-recursive-nameservers=10.10.10.10:53", "--dns01-recursive-nameservers-only", "--enable-certificate-owner-ref"}
			err := addOverrideArgs(certmanageroperatorclient, deployment.CertmanagerWebhookDeployment, args)
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for cert-manager webhook controller status to become degraded")
			err = waitForInvalidOperatorStatusCondition(certmanageroperatorclient, []string{deployment.CertManagerWebhookDeploymentControllerName})
			Expect(err).NotTo(HaveOccurred())

			By("Checking if the args are not added to the cert-manager webhook deployment")
			err = waitForDeploymentArgs(k8sClientSet, deployment.CertmanagerWebhookDeployment, args, false)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("When adding invalid cert-manager cainjector override args", func() {

		It("should not add the args to the cert-manager cainjector deployment", func() {

			By("Adding cert-manager cainjector override args to the cert-managaer operator object")
			args := []string{"--dns01-recursive-nameservers=10.10.10.10:53", "--dns01-recursive-nameservers-only", "--enable-certificate-owner-ref"}
			err := addOverrideArgs(certmanageroperatorclient, deployment.CertmanagerCAinjectorDeployment, args)
			Expect(err).NotTo(HaveOccurred())

			By("Waiting for cert-manager cainjector controller status to become degraded")
			err = waitForInvalidOperatorStatusCondition(certmanageroperatorclient, []string{deployment.CertManagerCAInjectorDeploymentControllerName})
			Expect(err).NotTo(HaveOccurred(), "Operator is expected to be available")

			By("Checking if the args are not added to the cert-manager cainjector deployment")
			err = waitForDeploymentArgs(k8sClientSet, deployment.CertmanagerCAinjectorDeployment, args, false)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	AfterAll(func() {
		By("Removing any existing overrides")
		err := removeOverrides(certmanageroperatorclient)
		Expect(err).NotTo(HaveOccurred())

		By("Waiting for operator status to become available")
		err = waitForValidOperatorStatusCondition(certmanageroperatorclient,
			[]string{deployment.CertManagerControllerDeploymentControllerName,
				deployment.CertManagerWebhookDeploymentControllerName,
				deployment.CertManagerCAInjectorDeploymentControllerName})
		Expect(err).NotTo(HaveOccurred(), "Operator is expected to be available")
	})
})
