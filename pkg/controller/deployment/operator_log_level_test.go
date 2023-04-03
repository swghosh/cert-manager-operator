package deployment

import (
	"fmt"
	"testing"

	operatorv1 "github.com/openshift/api/operator/v1"
	"k8s.io/klog/v2"
)

func TestSetOperatorLogLevel(t *testing.T) {
	testCases := []struct {
		logLevel              operatorv1.LogLevel
		desiredVerbosityLevel int
	}{
		{
			logLevel:              operatorv1.Normal,
			desiredVerbosityLevel: 2,
		},
		{
			logLevel:              operatorv1.Debug,
			desiredVerbosityLevel: 4,
		},
		{
			logLevel:              operatorv1.Trace,
			desiredVerbosityLevel: 6,
		},
		{
			logLevel:              operatorv1.TraceAll,
			desiredVerbosityLevel: 8,
		},
	}

	for _, testCase := range testCases {
		t.Run(fmt.Sprintf("logLevel %s", testCase.logLevel), func(t *testing.T) {
			setOperatorLogLevel(testCase.logLevel)

			for v := 1; v <= 10; v++ {
				expected := v <= testCase.desiredVerbosityLevel
				actual := klog.V(klog.Level(v)).Enabled()

				if actual != expected {
					t.Fatalf("Expected klog.V(%d) as %v but received %v", v, expected, actual)
				}
			}
		})
	}
}
