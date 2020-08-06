#!/bin/bash

#Usage: ../scripts/run_it.sh <acc_provision_input.yaml> <capic_admin_password>
docker run --rm -e "KUBECONFIG=/opflex-cni-test/data/kubeconfig" -e PROV_INP_FILE=$1 -e PSWD=$2 -e "GW_IP=14.3.0.1" --net=host -v ${HOME}:${HOME} -w $(pwd)/it -it jojimt/gobuild pytest -v -s -x
