package deployment

import (
	"strconv"

	"k8s.io/component-base/logs"
	"k8s.io/klog/v2"

	operatorv1 "github.com/openshift/api/operator/v1"
)

var operatorLogLevels = map[operatorv1.LogLevel]int{
	operatorv1.Normal:   2,
	operatorv1.Debug:    4,
	operatorv1.Trace:    6,
	operatorv1.TraceAll: 8,
}

// setOperatorLogLevel is used to set the value of klog verbosity
// if current verbosity level does not match logLevel
func setOperatorLogLevel(logLevel operatorv1.LogLevel) error {
	if logLevel == "" {
		logLevel = operatorv1.Normal
	}

	v := klog.Level(operatorLogLevels[logLevel])
	// set verbosity by checking if V(n) and V(n+1) are enabled,
	// change runtime verbosity level iff !V(n) or [V(n) and V(n+1)]
	if !klog.V(v).Enabled() || (klog.V(v).Enabled() && klog.V(v+1).Enabled()) {
		msg, err := logs.GlogSetter(strconv.Itoa(int(v)))
		if err != nil {
			return err
		}
		klog.V(2).Infof("operatorLogLevel: %q, %s", logLevel, msg)
	}
	return nil
}
