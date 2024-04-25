FROM brew.registry.redhat.io/rh-osbs/openshift-golang-builder:v1.20.12-202404151445.g5488123.el9 AS builder
WORKDIR /go/src/github.com/openshift/cert-manager-operator
COPY . .
RUN make build --warn-undefined-variables

FROM registry.access.redhat.com/ubi9-minimal:9.3
COPY --from=builder /go/src/github.com/openshift/cert-manager-operator/cert-manager-operator /usr/bin/

USER 65532:65532

ENTRYPOINT ["/usr/bin/cert-manager-operator"]
