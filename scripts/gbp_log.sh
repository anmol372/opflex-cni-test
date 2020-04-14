#!/bin/bash
pod=$(kubectl --kubeconfig=../data/kubeconfig get pods -A | grep "aci-containers-controller" | awk '{print $2}')
ns=$(kubectl --kubeconfig=../data/kubeconfig get pods -A | grep "aci-containers-controller" | awk '{print $1}')
kubectl --kubeconfig=../data/kubeconfig logs $pod -n $ns -c aci-gbpserver
