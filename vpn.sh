#!/bin/bash

nordvpn set lan-discovery enable

nordvpn connect

nordvpn status

echo "🌐 VPN setup complete."