package main

import (
	"context"
	"fmt"
	"time"

	"github.com/openshift/library-go/pkg/operator/events"
	"github.com/openshift/library-go/pkg/operator/resource/resourceapply"
	"github.com/openshift/library-go/pkg/operator/staticresourcecontroller"
	apiextensionsclient "k8s.io/apiextensions-apiserver/pkg/client/clientset/clientset"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"

	"github.com/openshift/cert-manager-operator/pkg/operator/assets"
	certmanoperatorclient "github.com/openshift/cert-manager-operator/pkg/operator/clientset/versioned"
	certmanoperatorinformers "github.com/openshift/cert-manager-operator/pkg/operator/informers/externalversions"
	"github.com/openshift/cert-manager-operator/pkg/operator/operatorclient"
)

var (
	startTime   time.Time
	runDuration time.Duration = 25 * time.Second
)

var (
	certManagerControllerAssetFiles = []string{
		"cert-manager-deployment/cert-manager-namespace.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-approve-cert-manager-io-cr.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-approve-cert-manager-io-crb.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-certificates-cr.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-certificates-crb.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-certificatesigningrequests-cr.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-certificatesigningrequests-crb.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-challenges-cr.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-challenges-crb.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-clusterissuers-cr.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-clusterissuers-crb.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-ingress-shim-cr.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-ingress-shim-crb.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-issuers-cr.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-issuers-crb.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-orders-cr.yaml",
		"cert-manager-deployment/controller/cert-manager-controller-orders-crb.yaml",
		"cert-manager-deployment/controller/cert-manager-edit-cr.yaml",
		"cert-manager-deployment/controller/cert-manager-leaderelection-rb.yaml",
		"cert-manager-deployment/controller/cert-manager-leaderelection-role.yaml",
		"cert-manager-deployment/controller/cert-manager-sa.yaml",
		"cert-manager-deployment/controller/cert-manager-svc.yaml",
		"cert-manager-deployment/controller/cert-manager-view-cr.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-approve-cert-manager-io-cr.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-approve-cert-manager-io-crb.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-certificatesigningrequests-cr.yaml",
		"cert-manager-deployment/cert-manager/cert-manager-controller-certificatesigningrequests-crb.yaml",
	}
)

func startTimer() {
	fmt.Println("start timer..")
	startTime = time.Now()
}

func main() {
	for _, assetName := range certManagerControllerAssetFiles {
		asset := assets.MustAsset(assetName)
		_ = asset
		// fmt.Printf("%s", asset)
		// fmt.Println("---")
	}

	kubeConfig, _ := clientcmd.BuildConfigFromFlags("", "/home/swghosh/.kube/config")
	kubeClient, _ := kubernetes.NewForConfig(kubeConfig)

	apiExtensionsClient, _ := apiextensionsclient.NewForConfig(kubeConfig)
	kubeClientContainer := resourceapply.NewKubeClientHolder(kubeClient).WithAPIExtensionsClient(apiExtensionsClient)

	certManagerOperatorClient, _ := certmanoperatorclient.NewForConfig(kubeConfig)

	opClient := operatorclient.OperatorClient{
		Informers: certmanoperatorinformers.NewSharedInformerFactory(certManagerOperatorClient, 10*time.Second),
		Client:    certManagerOperatorClient.OperatorV1alpha1(),
	}

	shouldCreateFn := func() bool {
		fmt.Println("shouldCreate()")
		return time.Since(startTime) < runDuration
	}
	shouldDeleteFn := func() bool {
		fmt.Println("shouldDelete()")
		return !shouldCreateFn()
	}

	assetNames := []string{"cmap1", "cmap2"}

	controller := staticresourcecontroller.NewStaticResourceController(
		"static-resource-test-controller", AssetGetter, assetNames, kubeClientContainer, opClient, events.NewInMemoryRecorder(""),
	).WithConditionalResources(AssetGetter, assetNames, shouldCreateFn, shouldDeleteFn)

	fmt.Println("Running Static Resource Controller...")
	startTimer()
	controller.Run(context.TODO(), 1)
}
