rm manifests.tmp.yaml
kubectl kustomize manifests/crds/ >> manifests.tmp.yaml
echo "---" >> manifests.tmp.yaml
kubectl kustomize manifests/operator/ >> manifests.tmp.yaml
cat manifests.tmp.yaml | helmify ../../Personal/homelab-harvester/charts/platform/kanidm/kanidm/charts/kanidm-operator
# cat manifests.tmp.yaml | helmify ../kanidm-operator-chart
