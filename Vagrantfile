# -*- mode: ruby -*-
# vi: set ft=ruby :

# nodes in cluster (excludes ecmp lb)
num_nodes = 2

# exported env vars
http_proxy = ENV['HTTP_PROXY'] || ENV['http_proxy'] || ''
https_proxy = ENV['HTTPS_PROXY'] || ENV['https_proxy'] || ''
no_proxy = ENV['NO_PROXY'] || ENV['no_proxy'] || ''

# common provisioning
provision_common_once = <<SCRIPT
cat >>/etc/profile.d/envvar.sh <<EOF
export http_proxy='#{http_proxy}'
export https_proxy='#{https_proxy}'
export no_proxy='#{no_proxy}',test-master,test-node1,test-node2,1.100.201.1,1.100.201.11,1.100.201.12,1.100.201.13
EOF
cat >>/etc/default/kubelet <<EOF
KUBELET_EXTRA_ARGS="--node-ip=#[node:ip]"
EOF
source /etc/profile.d/envvar.sh
mkdir -p /etc/systemd/system/docker.service.d
cat <<EOF >/etc/systemd/system/docker.service.d/docker-options.conf
[Service]
Environment="DOCKER_OPTS=  --graph=/var/lib/docker --log-opt max-size=50m --log-opt max-file=5 --iptables=false"
EOF

cat <<EOF >/etc/systemd/system/docker.service.d/http-proxy.conf
[Service]
Environment="HTTP_PROXY=#{http_proxy}"
Environment="HTTPS_PROXY=#{https_proxy}"
Environment="NO_PROXY=#{no_proxy}"
EOF

cat <<EOF >/etc/systemd/system/docker.service.d/docker-dns.conf
[Service]
Environment="DOCKER_DNS_OPTIONS=\
    --dns 172.28.184.18  \
    --dns-search default.svc.cluster.local --dns-search svc.cluster.local --dns-search noiro.lab  \
    --dns-opt ndots:2 --dns-opt timeout:2 --dns-opt attempts:2  \
"
EOF

mkdir -p /etc/docker
cat <<EOF >/etc/docker/daemon.json
{ "insecure-registries":["1.100.201.1:5000"] }
EOF

SCRIPT

nodemap = [
# lb must be the first entry in the list
  {
    :name => "lb",
    :roles => "lb",
    :box => "ubuntu/bionic64",
    :cpus => "2",
    :mem => "2048",
    :ip => "1.100.201.10"
  },
  {
    :name => "test-master",
    :roles => "master",
    :box => "ubuntu/bionic64",
    :cpus => "2",
    :mem => "2048",
    :ip => "1.100.201.11"
  },
  {
    :name => "test-node1",
    :roles => "node",
    :box => "ubuntu/bionic64",
    :cpus => "2",
    :mem => "2048",
    :ip => "1.100.201.12"
  },
  {
    :name => "test-node2",
    :roles => "node",
    :box => "ubuntu/bionic64",
    :cpus => "2",
    :mem => "2048",
    :ip => "1.100.201.13"
  }
]

master_ip = '1.100.201.11'
pod_network_cidr = '11.3.0.0/16'
count = 0

Vagrant.configure("2") do |config|
  nodemap.each do |node|
    if count > num_nodes then
      break
    end

    count = count + 1

    if count == 1 && ENV['SKIP_LB']
      next
    end

    config.vm.define node[:name] do |config|

      config.vm.hostname = node[:name]
      config.vm.box = node[:box]
      config.vm.box_check_update  = false
      config.vm.synced_folder "/tmp", "/mnt/tmp"
      config.vm.synced_folder "./data", "/home/vagrant/data"
      config.vm.network :private_network, ip: node[:ip]
      config.vm.provision "file", source: "/etc/resolv.conf", destination: "/home/vagrant/resolv.conf"
      config.vm.provision "shell" do |s|
        s.inline = provision_common_once
      end

      config.vm.provider 'virtualbox' do |vb|
        vb.linked_clone = true
        vb.name = node[:name]
        vb.memory = node[:mem].to_i
        vb.cpus = node[:cpus].to_i
      end   

      if node[:roles] == "lb"
        # Add your adapter to this list for automated configuration
        config.vm.network :private_network, ip: "1.201.201.201"
        config.vm.provision 'shell', path: 'scripts/provision_lb.sh', args: [master_ip, num_nodes]
      else
        config.vm.provision 'shell', path: 'scripts/provision_base.sh'
      end
     
      if node[:roles] == "master"
        config.vm.provision 'shell', path: 'scripts/provision_master.sh', args: [pod_network_cidr, num_nodes]
      elsif node[:roles] == "node"
        config.vm.provision 'shell', path: 'scripts/provision_node.sh', args: [master_ip]
      end
    end
  end
end
