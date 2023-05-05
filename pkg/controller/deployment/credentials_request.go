package deployment

import (
	"fmt"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	coreinformersv1 "k8s.io/client-go/informers/core/v1"
	"k8s.io/utils/pointer"

	configv1 "github.com/openshift/api/config/v1"
	"github.com/openshift/cert-manager-operator/pkg/operator/operatorclient"
	configinformersv1 "github.com/openshift/client-go/config/informers/externalversions/config/v1"

	v1 "github.com/openshift/api/operator/v1"
)

type cloudCredentialsConfig struct {
	mountDirectory string
	mountFilename  string

	secretKey string
}

const (
	// credentials for AWS
	awsCredentialsDir       = "/.aws"
	awsCredentialsFileName  = "credentials"
	awsCredentialsSecretKey = "credentials"

	// credentials for GCP
	gcpCredentialsDir       = "/.config/gcloud"
	gcpCredentialsFileName  = "application_default_credentials.json"
	gcpCredentialsSecretKey = "service_account.json"

	// cloudCredentialsVolumeName is the volume name for mounting
	// service account (gcp) or credentials (aws) file
	cloudCredentialsVolumeName = "cloud-credentials"

	// boundSA is the openshift bound service account
	// containing the sts token
	boundSATokenVolumeName = "bound-sa-token"
	boundSATokenDir        = "/var/run/secrets/openshift/serviceaccount"
	boundSAAudience        = "openshift"
	boundSAPath            = "token"
	boundSAExpirySec       = 3600
)

// currently supported cloud platforms for ambient credentialsare: AWS, GCP
var cloudCredentialConfigs = map[configv1.PlatformType]cloudCredentialsConfig{
	configv1.AWSPlatformType: {
		mountDirectory: awsCredentialsDir,
		mountFilename:  awsCredentialsFileName,

		secretKey: awsCredentialsSecretKey,
	},
	configv1.GCPPlatformType: {
		mountDirectory: gcpCredentialsDir,
		mountFilename:  gcpCredentialsFileName,

		secretKey: gcpCredentialsSecretKey,
	},
}

func withCloudCredentials(secretsInformer coreinformersv1.SecretInformer, infraInformer configinformersv1.InfrastructureInformer, deploymentName, secretName string) func(operatorSpec *v1.OperatorSpec, deployment *appsv1.Deployment) error {
	// cloud credentials is only required for the controller deployment,
	// other deployments should be left untouched
	if deploymentName != "cert-manager" {
		return func(operatorSpec *v1.OperatorSpec, deployment *appsv1.Deployment) error {
			return nil
		}
	}

	return func(operatorSpec *v1.OperatorSpec, deployment *appsv1.Deployment) error {
		volumes := []corev1.Volume{{
			Name: boundSATokenVolumeName,
			VolumeSource: corev1.VolumeSource{
				Projected: &corev1.ProjectedVolumeSource{
					DefaultMode: pointer.Int32(420),
					Sources: []corev1.VolumeProjection{{
						ServiceAccountToken: &corev1.ServiceAccountTokenProjection{
							Audience:          boundSAAudience,
							ExpirationSeconds: pointer.Int64(boundSAExpirySec),
							Path:              boundSAPath,
						}},
					},
				},
			},
		}}
		volumeMounts := []corev1.VolumeMount{{
			Name:      boundSATokenVolumeName,
			MountPath: boundSATokenDir,
			ReadOnly:  true,
		}}

		if len(secretName) > 0 {
			lister := secretsInformer.Lister()
			secretsLister := lister.Secrets(operatorclient.TargetNamespace)
			_, err := secretsLister.Get(secretName)
			// s, err := secretsInformer.Lister().Secrets(operatorclient.TargetNamespace).List(labels.Everything())
			// klog.V(2).Info(s)
			if err != nil {
				return err
			}

			if err != nil && apierrors.IsNotFound(err) {
				return fmt.Errorf("(Retrying) cloud secret %q doesn't exist due to %v", secretName, err)
			} else if err != nil {
				return err
			}

			infra, err := infraInformer.Lister().Get("cluster")
			if err != nil {
				return err
			}

			cloudProvider := infra.Status.PlatformStatus.Type
			if cloudCredentialConfig, ok := cloudCredentialConfigs[cloudProvider]; ok {
				// supported cloud platform for mounting secrets found
				volumes = append(volumes, corev1.Volume{
					Name: cloudCredentialsVolumeName,
					VolumeSource: corev1.VolumeSource{
						Secret: &corev1.SecretVolumeSource{
							SecretName: secretName,
							Items: []corev1.KeyToPath{{
								Key:  cloudCredentialConfig.secretKey,
								Path: cloudCredentialConfig.mountFilename,
							}},
						},
					},
				})
				volumeMounts = append(volumeMounts, corev1.VolumeMount{
					Name:      cloudCredentialsVolumeName,
					MountPath: cloudCredentialConfig.mountDirectory,
				})
			}
		}

		deployment.Spec.Template.Spec.Volumes = append(
			deployment.Spec.Template.Spec.Volumes,
			volumes...,
		)
		deployment.Spec.Template.Spec.Containers[0].VolumeMounts = append(
			deployment.Spec.Template.Spec.Containers[0].VolumeMounts,
			volumeMounts...,
		)

		return nil
	}
}
