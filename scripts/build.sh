#!/bin/bash
git clone https://github.com/noironetworks/aci-containers -b demo
cd aci-containers
dep ensure -v
# fix etcd repo issue
rm vendor/github.com/coreos/etcd/client/keys.generated.go
make go-build
export DOCKER_HUB_ID=1.100.201.1:5000
make container-gbpserver
docker tag 1.100.201.1:5000/gbpserver 1.100.201.1:5000/gbpserver:ci_test
docker push 1.100.201.1:5000/gbpserver:ci_test
