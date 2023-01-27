FROM docker.io/golang:1.19 AS builder
WORKDIR /go/src/github.com/openshift/cert-manager-operator
COPY . .
RUN make build --warn-undefined-variables

FROM docker.io/redhat/ubi9-minimal:9.1
COPY --from=builder /go/src/github.com/openshift/cert-manager-operator/cert-manager-operator /usr/bin/

USER 65532:65532

ENTRYPOINT ["/usr/bin/cert-manager-operator"]
