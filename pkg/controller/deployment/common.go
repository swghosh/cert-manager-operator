package deployment

const (
	operatorName      = "cert-manager"
	operandNamePrefix = ""
	conditionsPrefix  = "CertManager"

	CertmanagerControllerDeployment = "cert-manager"
	CertmanagerWebhookDeployment    = "cert-manager-webhook"
	CertmanagerCAinjectorDeployment = "cert-manager-cainjector"
)
