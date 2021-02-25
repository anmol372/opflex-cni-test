#!/bin/bash
export DEBIAN_FRONTEND=noninteractive

POD_NETWORK_CIDR=$1
NUM_NODES=$2

IP=`ip -4 addr show dev enp0s8 | grep inet | awk '{print $2}' | cut -f1 -d/`
HOST_NAME=$(hostname -s)
SERVICE_TOPOLOGY='true'
echo "Executing inside node $HOST_NAME"
echo "Provisioning $NUM_NODES nodes"

echo "Starting kubeadm init"
KUBEADM_CONFIG=$(cat <<-EOF
apiVersion: kubeadm.k8s.io/v1beta2
bootstrapTokens:
- groups:
  - system:bootstrappers:kubeadm:default-node-token
  token: abcdef.0123456789abcdef
  ttl: 24h0m0s
  usages:
  - signing
  - authentication
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: $IP
  bindPort: 6443
nodeRegistration:
  criSocket: /var/run/dockershim.sock
  name: $HOST_NAME
  taints:
  - effect: NoSchedule
    key: node-role.kubernetes.io/master
---
apiVersion: kubeadm.k8s.io/v1beta2
kind: ClusterConfiguration
networking:
  dnsDomain: cluster.local
  podSubnet: "11.3.0.0/16"
controllerManager:
  extraArgs:
    feature-gates: ServiceTopology=true
apiServer:
  extraArgs:
    feature-gates: ServiceTopology=true
EOF
)
echo "${KUBEADM_CONFIG}"  > /tmp/config.yaml

kubeadm init --config /tmp/config.yaml

echo "Copying admin credendtials to vagrant user"
sudo --user=vagrant mkdir -p /home/vagrant/.kube
cp -i /etc/kubernetes/admin.conf /home/vagrant/.kube/config
cp /etc/kubernetes/admin.conf /home/vagrant/data/kubeconfig
chown $(id -u vagrant):$(id -g vagrant) /home/vagrant/.kube/config

echo "Creating kubeadm token for join"
kubeadm token create --print-join-command >> /bin/kubeadm_join.sh
chmod +x /bin/kubeadm_join.sh

export KUBECONFIG=/etc/kubernetes/admin.conf

sudo mkdir -p /kubeconfig
sudo chmod 777 /kubeconfig
kubectl config view > /kubeconfig/kube.yaml

echo "Configuring kafka secrets"
CERT_DIR=/home/vagrant/data/kafka-k8s/tls-certs
pushd ${CERT_DIR}

kubectl create secret generic kafka-certificates --from-file=${CERT_DIR}/kafka.keystore.jks --from-file=./kafka.truststore.jks

kubectl create secret generic kafka-client-certificates --from-file=./ca.crt --from-file=./kafka-client.crt --from-file=./kafka-client.key -n kube-system

kubectl create secret generic kafka-kv-certificates --from-file=./ca.crt --from-file=./kafka-client.crt --from-file=./kafka-client.key

popd

echo "Configuring aci cni"
kubectl apply -f /home/vagrant/data/aci_deployment.yaml


echo "Changing kube-proxy to use 1.100.201.0/24 for NODE_PORT masquerade"
kubectl get daemonset kube-proxy -n kube-system  -o yaml > /tmp/kp.yaml
kubectl delete -f /tmp/kp.yaml
sed -i "/.*hostname-override.*/a\ \ \ \ \ \ \ \ - --nodeport-addresses=1.100.201.0/24" /tmp/kp.yaml
kubectl apply -f /tmp/kp.yaml

if [ $NUM_NODES -lt 3 ]; then
    kubectl taint nodes test-master node-role.kubernetes.io/master:NoSchedule-
fi

echo "Done provisioning $HOST_NAME"
