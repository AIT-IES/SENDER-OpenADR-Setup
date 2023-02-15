# connections from outside
iptables -I FORWARD -o br0 -d  10.28.60.52 -j ACCEPT
iptables -t nat -I PREROUTING -p tcp --dport 8080 -j DNAT --to 10.28.60.52:8080

# Masquerade local subnet
iptables -t nat -A POSTROUTING -s 10.28.60.0/24 -j MASQUERADE
iptables -A FORWARD -o br0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i br0 -o eno1 -j ACCEPT
iptables -A FORWARD -i br0 -o lo -j ACCEPT