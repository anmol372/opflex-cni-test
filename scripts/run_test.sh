#!/bin/bash
docker run --rm -e "KUBECONFIG=/opflex-cni-test/data/kubeconfig" --net=host -v $PWD:/opflex-cni-test -w /opflex-cni-test/test -it noirolabs/gobuild pytest -v -s -x
