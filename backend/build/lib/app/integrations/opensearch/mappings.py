from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import Settings


@dataclass(frozen=True)
class OpenSearchSourceMapping:
    name: str
    index_pattern: str
    timestamp_field: str

    source_ip_fields: list[str]
    destination_ip_fields: list[str]

    source_port_fields: list[str] = field(default_factory=list)
    destination_port_fields: list[str] = field(default_factory=list)

    protocol_fields: list[str] = field(default_factory=list)
    action_fields: list[str] = field(default_factory=list)
    application_fields: list[str] = field(default_factory=list)
    rule_fields: list[str] = field(default_factory=list)
    policy_fields: list[str] = field(default_factory=list)
    user_fields: list[str] = field(default_factory=list)
    domain_fields: list[str] = field(default_factory=list)
    url_fields: list[str] = field(default_factory=list)

    bytes_fields: list[str] = field(default_factory=list)
    packets_fields: list[str] = field(default_factory=list)

    # Extra fields specific to this source
    extra_fields: list[str] = field(default_factory=list)

    block_actions: set[str] = field(default_factory=set)


def build_source_mappings(settings: Settings) -> list[OpenSearchSourceMapping]:
    """Return the list of OpenSearch source mappings for all configured indices."""
    return [
        # --- 1. CISCO ASA (SYSLOG) ---
        OpenSearchSourceMapping(
            name="cisco_asa",
            index_pattern=settings.opensearch_cisco_asa_index_pattern,
            timestamp_field="@timestamp",
            source_ip_fields=["source.ip"],
            destination_ip_fields=["destination.ip"],
            source_port_fields=["source.port"],
            destination_port_fields=["destination.port"],
            protocol_fields=["network.transport", "network.connection.id"],
            action_fields=["event.action", "event.category", "event.type"],
            application_fields=[],
            rule_fields=[],
            policy_fields=[],
            user_fields=[],
            domain_fields=[],
            url_fields=["message"],
            bytes_fields=[],
            packets_fields=[],
            extra_fields=["device_type", "observer.product", "observer.vendor", "tags"],
            block_actions={"deny", "drop", "blocked", "block"},
        ),

        # --- 2. CISCO FIREPOWER FTD (SYSLOG) ---
        OpenSearchSourceMapping(
            name="firepower",
            index_pattern=settings.opensearch_firepower_index_pattern,
            timestamp_field="@timestamp",
            source_ip_fields=["source.ip"],
            destination_ip_fields=["destination.ip"],
            source_port_fields=["source.port"],
            destination_port_fields=["destination.port"],
            protocol_fields=["network.transport", "network.direction"],
            action_fields=["event.action", "event.category", "event.type"],
            application_fields=[],
            rule_fields=[],
            policy_fields=[],
            user_fields=[],
            domain_fields=[],
            url_fields=["message"],
            bytes_fields=["network.bytes"],
            packets_fields=[],
            extra_fields=[
                "device_type", "observer.product", "observer.vendor",
                "source.geo.country_name", "destination.geo.country_name",
                "tcp.flags", "icmp.code", "icmp.type",
                "vpn.group", "tags", "type",
            ],
            block_actions={"deny", "drop", "blocked", "block"},
        ),

        # --- 3. CISCO FMC (ESTREAMER) ---
        OpenSearchSourceMapping(
            name="fmc_estreamer",
            index_pattern=settings.opensearch_fmc_estreamer_index_pattern,
            timestamp_field="@timestamp",
            source_ip_fields=[
                "initiator_ip",
                "original_initiator_ip",
                "extra_fields.NAT_InitiatorIP",
            ],
            destination_ip_fields=[
                "responder_ip",
                "extra_fields.NAT_ResponderIP",
            ],
            source_port_fields=[
                "initiator_port",
                "extra_fields.NAT_InitiatorPort",
            ],
            destination_port_fields=[
                "responder_port",
                "extra_fields.NAT_ResponderPort",
            ],
            protocol_fields=["protocol"],
            action_fields=[
                "extra_fields.AC_RuleAction",
                "event_type.keyword",
                "event_type",
            ],
            application_fields=[
                "application.keyword",
                "application",
                "client_application.keyword",
                "client_application",
                "client_app_detector.keyword",
                "web_application.keyword",
                "web_application",
            ],
            rule_fields=[
                "firewall_rule.keyword",
                "firewall_rule",
            ],
            policy_fields=[
                "firewall_policy.keyword",
                "firewall_policy",
                "prefilter_policy.keyword",
                "prefilter_policy",
            ],
            user_fields=[
                "extra_fields.UserName.keyword",
                "extra_fields.UserName",
            ],
            domain_fields=[
                "referenced_host.keyword",
                "referenced_host",
                "extra_fields.DNS_Query.keyword",
                "extra_fields.DNS_Query",
            ],
            url_fields=[
                "url.keyword",
                "url",
                "extra_fields.URI.keyword",
                "extra_fields.URI",
                "extra_fields.HTTP_Referer.keyword",
                "extra_fields.HTTP_Referer",
            ],
            bytes_fields=["initiator_bytes", "responder_bytes"],
            packets_fields=["initiator_packets", "responder_packets"],
            extra_fields=[
                "connection_id", "connection_duration",
                "device_location", "device_uuid",
                "ingress_zone", "egress_zone",
                "ingress_interface", "egress_interface",
                "vlan_id",
                "extra_fields.SSL_Version",
                "extra_fields.SSL_CipherSuite",
                "extra_fields.FileAction",
                "extra_fields.FileName",
                "extra_fields.FileType",
                "extra_fields.VPN_Action",
                "extra_fields.NetBIOS_Domain",
                "extra_fields.NAT_InitiatorIP",
                "extra_fields.NAT_ResponderIP",
                "geo_initiator.geo.country_name",
                "geo_responder.geo.country_name",
            ],
            block_actions={"block", "blocked", "deny", "denied", "drop", "dropped"},
        ),

        # --- 4. CISCO USER ACTIVITY (FMC REST API) ---
        OpenSearchSourceMapping(
            name="cisco_user_activity",
            index_pattern=settings.opensearch_cisco_user_activity_index_pattern,
            timestamp_field="@timestamp",
            source_ip_fields=["ipAddress", "vpnClientPublicIP"],
            destination_ip_fields=[],
            source_port_fields=[],
            destination_port_fields=[],
            protocol_fields=[],
            action_fields=["event", "event_type", "authenticationType"],
            application_fields=["discoveryApplication", "vpnClientApplication"],
            rule_fields=[],
            policy_fields=["vpnConnectionProfile", "vpnGroupPolicy"],
            user_fields=["username", "realmName"],
            domain_fields=[],
            url_fields=[],
            bytes_fields=["vpnBytesIn", "vpnBytesOut"],
            packets_fields=[],
            extra_fields=[
                "device", "description",
                "endpointLocation", "endpointProfile",
                "securityGroupTag",
                "vpnSessionType", "vpnConnectionDuration",
                "vpnClientCountry", "vpnClientOS",
            ],
            block_actions=set(),
        ),

        # --- 5. CHECKPOINT SYSLOG ---
        OpenSearchSourceMapping(
            name="checkpoint",
            index_pattern=settings.opensearch_checkpoint_index_pattern,
            timestamp_field="@timestamp",
            source_ip_fields=[
                "src",
                "client_ip.keyword",
                "client_ip",
                "endpoint_ip.keyword",
                "endpoint_ip",
                "xlatesrc",
                "proxy_src_ip.keyword",
                "proxy_src_ip",
                "origin",
            ],
            destination_ip_fields=[
                "dst",
                "xlatedst",
            ],
            source_port_fields=[
                "s_port",
                "xlatesport.keyword",
                "xlatesport",
            ],
            destination_port_fields=[
                "service",
                "__p_dport.keyword",
                "__p_dport",
                "xlatedport.keyword",
                "xlatedport",
            ],
            protocol_fields=[
                "proto.keyword",
                "proto",
                "protocol.keyword",
                "protocol",
            ],
            action_fields=[
                "action.keyword",
                "action",
                "rule_action.keyword",
                "rule_action",
            ],
            application_fields=[
                "appi_name.keyword",
                "appi_name",
                "app_id.keyword",
                "app_id",
                "app_category.keyword",
                "app_category",
                "app_desc.keyword",
            ],
            rule_fields=[
                "rule_name.keyword",
                "rule_name",
                "rule.keyword",
                "rule",
                "rule_uid.keyword",
                "rule_uid",
            ],
            policy_fields=[
                "policy.keyword",
                "policy",
                "layer_name.keyword",
                "layer_name",
                "sub_policy_name.keyword",
                "sub_policy_name",
            ],
            user_fields=[
                "user.keyword",
                "user",
                "src_user_name.keyword",
                "src_user_name",
                "dst_user_name.keyword",
                "dst_user_name",
                "administrator.keyword",
            ],
            domain_fields=[
                "domain.keyword",
                "domain",
                "domain_name.keyword",
                "domain_name",
                "src_domain_name.keyword",
                "src_domain_name",
                "dst_domain_name.keyword",
                "dst_domain_name",
                "http_host.keyword",
                "http_host",
                "sni.keyword",
                "sni",
                "tls_server_host_name.keyword",
                "tls_server_host_name",
            ],
            url_fields=[
                "resource.keyword",
                "resource",
                "url.keyword",
                "url",
                "referrer.keyword",
                "referrer",
            ],
            bytes_fields=[
                "bytes",
                "client_inbound_bytes",
                "client_outbound_bytes",
                "server_inbound_bytes",
                "server_outbound_bytes",
            ],
            packets_fields=[
                "packets",
                "client_inbound_packets",
                "client_outbound_packets",
                "server_inbound_packets",
                "server_outbound_packets",
            ],
            extra_fields=[
                "product", "description", "severity",
                "blade_name", "inzone", "outzone",
                "ifname", "ifdir",
                "conn_direction", "connection_count",
                "elapsed", "start_time",
                "session_uid", "session_id",
                "originsicname", "srcname",
                "attack", "attack_info",
                "malware_action", "malware_family",
                "protection_name", "protection_type",
                "sensor_alert_title", "sensor_alert_type",
                "identity_src", "identity_type",
                "certificate_resource", "certificate_validation",
                "content_type", "content_disposition",
                "method", "http_status",
                "os_name", "os_version",
                "client_name", "client_version",
                "src_machine_name", "dst_machine_name",
                "email_id", "email_recipients_num",
                "icmp", "icmp_code", "icmp_type",
                "tcp_flags",
            ],
            block_actions={
                "drop", "dropped", "deny", "denied",
                "reject", "prevent", "blocked", "block",
            },
        ),
    ]


# --- Painless scripts for composite aggregations ---

DOMAIN_EXTRACTION_SCRIPT = """
String[] fields = new String[] {
  'extra_fields.DNS_Query.keyword',
  'question_rdata.keyword',
  'sni.keyword',
  'tls_server_host_name.keyword',
  'http_host.keyword',
  'referenced_host.keyword',
  'dst_domain_name.keyword',
  'domain_name.keyword',
  'domain.keyword',
  'resource.keyword',
  'url.keyword'
};

for (String field : fields) {
  if (!doc.containsKey(field) || doc[field].size() == 0) {
    continue;
  }
  String value = doc[field].value;
  if (value == null) { continue; }
  value = value.trim().toLowerCase();
  if (value.length() == 0 || value == '-' || value == 'null') { continue; }

  int schemePos = value.indexOf('://');
  if (schemePos >= 0) { value = value.substring(schemePos + 3); }
  else if (value.startsWith('//')) { value = value.substring(2); }

  int atPos = value.lastIndexOf('@');
  if (atPos >= 0) { value = value.substring(atPos + 1); }

  int slashPos = value.indexOf('/');
  if (slashPos >= 0) { value = value.substring(0, slashPos); }

  int queryPos = value.indexOf('?');
  if (queryPos >= 0) { value = value.substring(0, queryPos); }

  int fragmentPos = value.indexOf('#');
  if (fragmentPos >= 0) { value = value.substring(0, fragmentPos); }

  if (!value.startsWith('[')) {
    int colonPos = value.indexOf(':');
    if (colonPos >= 0) { value = value.substring(0, colonPos); }
  }

  while (value.endsWith('.')) { value = value.substring(0, value.length() - 1); }

  if (value.length() > 0 && value != '-' && value != 'null' && value.indexOf(' ') == -1) {
    return value;
  }
}
return 'unknown';
"""

APPLICATION_EXTRACTION_SCRIPT = """
String[] fields = new String[] {
  'application.keyword',
  'client_application.keyword',
  'client_app_detector.keyword',
  'appi_name.keyword',
  'app_desc.keyword',
  'app_id.keyword',
  'protocol.keyword',
  'proto.keyword'
};

for (String field : fields) {
  if (!doc.containsKey(field) || doc[field].size() == 0) {
    continue;
  }
  String value = doc[field].value;
  if (value != null) {
    value = value.trim();
    if (value.length() > 0 && value != '-' && value.toLowerCase() != 'null') {
      return value;
    }
  }
}
return 'Unknown';
"""
