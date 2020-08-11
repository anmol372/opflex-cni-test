#!/bin/bash
docker run --rm -e "KUBECONFIG=/opflex-cni-test/data/kubeconfig" -e LOG_LEVEL=$2 -e "GW_IP=14.3.0.1" --net=host -v $PWD:/opflex-cni-test -w /opflex-cni-test/test -it noirolabs/gobuild pytest -v -s -x test_basic.py test_default.py test_dns.py test_ovs_restart.py test_basic.py test_default.py
