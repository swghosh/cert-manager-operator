package deployment

import (
	"fmt"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	coreinformersv1 "k8s.io/client-go/informers/core/v1"
	"k8s.io/utils/pointer"

	v1 "github.com/openshift/api/operator/v1"
	"github.com/openshift/cert-manager-operator/pkg/operator/operatorclient"
)

type cloudCredentialsConfig struct {
	mountDirectory string
	mountFilename  string

	secretName string
	secretKey  string
}

const (
	// credentials for AWS
	awsCredentialsDir        = "/.aws"
	awsCredentialsFileName   = "credentials"
	awsCredentialsSecretKey  = "credentials"
	awsCredentialsSecretName = "aws-creds"

	// credentials for GCP
	gcpCredentialsDir       = "/.config/gcloud"
	gcpCredentialsFileName  = "application_default_credentials.json"
	gcpCredentialsSecretKey = "service_account.json"
	gcpCredentialsSeretName = "gcp-credentials"

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

var cloudCredentialConfigs = map[string]cloudCredentialsConfig{
	"aws": {
		mountDirectory: awsCredentialsDir,
		mountFilename:  awsCredentialsFileName,

		secretName: awsCredentialsSecretName,
		secretKey:  awsCredentialsSecretKey,
	},
	"gcp": {
		mountDirectory: gcpCredentialsDir,
		mountFilename:  gcpCredentialsFileName,

		secretName: gcpCredentialsSeretName,
		secretKey:  gcpCredentialsSecretKey,
	},
}

func withCloudCredentials(secretsInformer coreinformersv1.SecretInformer, deploymentName string) func(operatorSpec *v1.OperatorSpec, deployment *appsv1.Deployment) error {
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

		for cloudProviderName := range cloudCredentialConfigs {
			_, err := secretsInformer.Lister().Secrets(operatorclient.TargetNamespace).Get(
				cloudCredentialConfigs[cloudProviderName].secretName)
			if err != nil {
				if errors.IsNotFound(err) {
					continue
				} else {
					return err
				}
			}

			volName := fmt.Sprintf("%s-%s", cloudProviderName, cloudCredentialsVolumeName)
			volumes = append(volumes, corev1.Volume{
				Name: volName,
				VolumeSource: corev1.VolumeSource{
					Secret: &corev1.SecretVolumeSource{
						SecretName: cloudCredentialConfigs[cloudProviderName].secretName,
						Items: []corev1.KeyToPath{{
							Key:  cloudCredentialConfigs[cloudProviderName].secretKey,
							Path: cloudCredentialConfigs[cloudProviderName].mountFilename,
						}},
					},
				},
			})
			volumeMounts = append(volumeMounts, corev1.VolumeMount{
				Name:      volName,
				MountPath: cloudCredentialConfigs[cloudProviderName].mountDirectory,
			})

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
