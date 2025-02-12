package v1alpha1

import (
	"path/filepath"
	"testing"

	"sigs.k8s.io/controller-runtime/pkg/envtest"
)

func TestCertManagerCRD(t *testing.T) {
	testEnv := &envtest.Environment{
		CRDDirectoryPaths:     []string{filepath.Join("..", "config", "crd", "bases")},
		ErrorIfCRDPathMissing: true,
	}

	//start testEnv
	cfg, err := testEnv.Start()
	_ = cfg
	_ = err

	//stop testEnv
	err = testEnv.Stop()
	_ = err
}
