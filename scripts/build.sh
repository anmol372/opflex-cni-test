#!/bin/bash
if [ -z "$SKIP_CLONE" ]
then 
  git clone https://github.com/noironetworks/aci-containers
fi
cd aci-containers
make go-build
export DOCKER_HUB_ID=1.100.201.1:5000
make container-gbpserver
docker tag 1.100.201.1:5000/gbp-server 1.100.201.1:5000/gbp-server:ci_test
docker push 1.100.201.1:5000/gbp-server:ci_test
make container-host
docker tag 1.100.201.1:5000/aci-containers-host 1.100.201.1:5000/aci-containers-host:ci_test
docker push 1.100.201.1:5000/aci-containers-host:ci_test
make container-controller
docker tag 1.100.201.1:5000/aci-containers-controller 1.100.201.1:5000/aci-containers-controller:ci_test
docker push 1.100.201.1:5000/aci-containers-controller:ci_test
