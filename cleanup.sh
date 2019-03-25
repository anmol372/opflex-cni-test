#!/bin/bash
docker rm -f $(docker ps | grep registry | awk '{print $1}')
vagrant destroy -f
sudo rm -rf ${GOPATH}/src/aci-containers

