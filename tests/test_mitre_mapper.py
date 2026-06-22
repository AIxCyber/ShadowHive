"""Unit tests for MITRE ATT&CK rule-based mapping."""

from backend.services.mitre_mapper import EVENT_TYPE_RULES, rule_based_match


class TestCommandBasedRules:
    def test_powershell(self):
        result = rule_based_match("cowrie.command.input", "powershell -enc AQBhAGQAbQBlAG4A")
        assert result is not None
        assert result["technique_id"] == "T1059.001"
        assert result["tactic"] == "execution"

    def test_unix_shell_commands(self):
        result = rule_based_match("cowrie.command.input", "ls -la /home")
        assert result["technique_id"] == "T1083"
        assert result["tactic"] == "discovery"

        result = rule_based_match("cowrie.command.input", "cat /etc/passwd")
        assert result["technique_id"] == "T1083"

    def test_system_discovery(self):
        result = rule_based_match("cowrie.command.input", "whoami")
        assert result["technique_id"] == "T1082"
        assert result["tactic"] == "discovery"

        result = rule_based_match("cowrie.command.input", "uname -a")
        assert result["technique_id"] == "T1082"

    def test_remote_services(self):
        result = rule_based_match("cowrie.command.input", "ssh root@192.168.1.1")
        assert result["technique_id"] == "T1021"
        assert result["tactic"] == "lateral-movement"

    def test_network_discovery(self):
        result = rule_based_match("cowrie.command.input", "nmap -sV 10.0.0.0/24")
        assert result["technique_id"] == "T1046"
        assert result["tactic"] == "discovery"

        result = rule_based_match("cowrie.command.input", "netstat -tulpn")
        assert result["technique_id"] == "T1046"

    def test_indicator_removal(self):
        result = rule_based_match("cowrie.command.input", "rm -rf /var/log")
        assert result["technique_id"] == "T1070.004"
        assert result["tactic"] == "defense-evasion"

    def test_credential_access(self):
        result = rule_based_match("cowrie.command.input", "strings /etc/shadow")
        assert result["technique_id"] == "T1003"
        assert result["tactic"] == "credential-access"

    def test_no_match_returns_none(self):
        result = rule_based_match("cowrie.command.input", "echo hello")
        assert result is None


class TestEventTypeRules:
    def test_all_event_types_covered(self):
        for event_type, expected in EVENT_TYPE_RULES.items():
            result = rule_based_match(event_type, "")
            assert result is not None, f"No match for {event_type}"
            assert result["technique_id"] == expected["technique_id"]
            assert result["tactic"] == expected["tactic"]

    def test_command_takes_precedence(self):
        result = rule_based_match("cowrie.login.success", "whoami")
        assert result["technique_id"] == "T1082"

    def test_unknown_event_type(self):
        result = rule_based_match("cowrie.unknown.event", "")
        assert result is None

    def test_lateral_movement_on_connect(self):
        result = rule_based_match("cowrie.session.connect", "")
        assert result["technique_id"] == "T1021"

    def test_brute_force_on_failed_login(self):
        result = rule_based_match("cowrie.login.failed", "")
        assert result["technique_id"] == "T1110"

    def test_valid_accounts_on_successful_login(self):
        result = rule_based_match("cowrie.login.success", "")
        assert result["technique_id"] == "T1078"

    def test_command_with_blank_args(self):
        result = rule_based_match("cowrie.command.input", None)
        assert result is None

        result = rule_based_match("cowrie.command.input", "")
        assert result is None


class TestNewOpenCanaryRules:
    def test_ftp_login(self):
        result = rule_based_match("opencanary.ftp.login", "")
        assert result is not None
        assert result["technique_id"] == "T1110"
        assert result["tactic"] == "credential-access"
        assert isinstance(result["confidence"], float)

    def test_smb_access(self):
        result = rule_based_match("opencanary.smb.access", "")
        assert result["technique_id"] == "T1021"
        assert result["tactic"] == "lateral-movement"

    def test_rdp_login(self):
        result = rule_based_match("opencanary.rdp.login", "")
        assert result["technique_id"] == "T1021"

    def test_vnc_login(self):
        result = rule_based_match("opencanary.vnc.login", "")
        assert result["technique_id"] == "T1021"

    def test_http_request(self):
        result = rule_based_match("opencanary.http.request", "")
        assert result["technique_id"] == "T1190"
        assert result["tactic"] == "initial-access"

    def test_sip_call(self):
        result = rule_based_match("opencanary.sip.call", "")
        assert result["technique_id"] == "T1071.001"
        assert result["tactic"] == "command-and-control"

    def test_tftp_request(self):
        result = rule_based_match("opencanary.tftp.request", "")
        assert result["technique_id"] == "T1048"
        assert result["tactic"] == "exfiltration"

    def test_git_clone(self):
        result = rule_based_match("opencanary.git.clone", "")
        assert result["technique_id"] == "T1552.001"
        assert result["tactic"] == "credential-access"


class TestNewWebHoneypotRules:
    def test_wp_login(self):
        result = rule_based_match("web.wp_login", "")
        assert result["technique_id"] == "T1078"
        assert result["tactic"] == "defense-evasion"

    def test_phpmyadmin(self):
        result = rule_based_match("web.phpmyadmin", "")
        assert result["technique_id"] == "T1190"
        assert result["tactic"] == "initial-access"

    def test_jenkins_login(self):
        result = rule_based_match("web.jenkins_login", "")
        assert result["technique_id"] == "T1078"

    def test_gitlab_login(self):
        result = rule_based_match("web.gitlab_login", "")
        assert result["technique_id"] == "T1078"

    def test_vpn_login(self):
        result = rule_based_match("web.vpn_login", "")
        assert result["technique_id"] == "T1133"
        assert result["tactic"] == "initial-access"

    def test_api_key_harvest(self):
        result = rule_based_match("web.api_key_harvest", "")
        assert result["technique_id"] == "T1528"
        assert result["tactic"] == "credential-access"


class TestNewDionaeaRules:
    def test_malware_download(self):
        result = rule_based_match("dionaea.malware.download", "")
        assert result["technique_id"] == "T1204"
        assert result["tactic"] == "execution"

    def test_smb_access(self):
        result = rule_based_match("dionaea.smb.access", "")
        assert result["technique_id"] == "T1021"
        assert result["tactic"] == "lateral-movement"

    def test_mssql_login(self):
        result = rule_based_match("dionaea.mssql.login", "")
        assert result["technique_id"] == "T1110"
        assert result["tactic"] == "credential-access"

    def test_mssql_query(self):
        result = rule_based_match("dionaea.mssql.query", "")
        assert result["technique_id"] == "T1213"
        assert result["tactic"] == "collection"

    def test_connection(self):
        result = rule_based_match("dionaea.connection", "")
        assert result["technique_id"] == "T1046"
        assert result["tactic"] == "discovery"

    def test_dionaea_http_request(self):
        result = rule_based_match("dionaea.http.request", "")
        assert result["technique_id"] == "T1190"
        assert result["tactic"] == "initial-access"

    def test_sip_call(self):
        result = rule_based_match("dionaea.sip.call", "")
        assert result["technique_id"] == "T1071.001"

    def test_tftp_request(self):
        result = rule_based_match("dionaea.tftp.request", "")
        assert result["technique_id"] == "T1048"


class TestNewWordPressRules:
    def test_login_attempt(self):
        result = rule_based_match("wp.login_attempt", "")
        assert result["technique_id"] == "T1110"
        assert result["tactic"] == "credential-access"

    def test_plugin_scan(self):
        result = rule_based_match("wp.plugin_scan", "")
        assert result["technique_id"] == "T1046"
        assert result["tactic"] == "discovery"

    def test_xmlrpc_attack(self):
        result = rule_based_match("wp.xmlrpc_attack", "")
        assert result["technique_id"] == "T1190"
        assert result["tactic"] == "initial-access"


class TestURLPathRules:
    def test_wp_login_path(self):
        result = rule_based_match("web", "/wp-login.php")
        assert result is not None
        assert result["technique_id"] == "T1078"

    def test_phpmyadmin_path(self):
        result = rule_based_match("web", "/phpmyadmin/index.php")
        assert result is not None
        assert result["technique_id"] == "T1190"

    def test_jenkins_path(self):
        result = rule_based_match("web", "/jenkins/login")
        assert result is not None
        assert result["technique_id"] == "T1078"

    def test_gitlab_path(self):
        result = rule_based_match("web", "/gitlab/users/sign_in")
        assert result is not None
        assert result["technique_id"] == "T1078"

    def test_webmail_path(self):
        result = rule_based_match("web", "/webmail/login")
        assert result is not None
        assert result["technique_id"] == "T1078"

    def test_vpn_path(self):
        result = rule_based_match("web", "/vpn/login")
        assert result is not None
        assert result["technique_id"] == "T1133"
        assert result["tactic"] == "initial-access"

    def test_http_event_type(self):
        result = rule_based_match("http", "/wp-login.php")
        assert result is not None
        assert result["technique_id"] == "T1078"

    def test_no_path_match_returns_none(self):
        result = rule_based_match("web", "/some-other-path")
        assert result is None


class TestConfidenceScores:
    def test_confidence_is_float(self):
        for event_type in EVENT_TYPE_RULES:
            result = rule_based_match(event_type, "")
            assert isinstance(result["confidence"], float), f"{event_type} confidence not float"
            assert 0 < result["confidence"] <= 1.0, f"{event_type} confidence out of range"

    def test_high_confidence_for_known_attacks(self):
        result = rule_based_match("cowrie.login.failed", "")
        assert result["confidence"] > 0.8

        result = rule_based_match("web.api_key_harvest", "")
        assert result["confidence"] > 0.85

    def test_lower_confidence_for_generic_events(self):
        result = rule_based_match("cowrie.client.size", "")
        assert result["confidence"] <= 0.5

        result = rule_based_match("dionaea.sip.call", "")
        assert result["confidence"] <= 0.5
    
    def test_command_rules_have_high_confidence(self):
        result = rule_based_match("cowrie.command.input", "whoami")
        assert result["confidence"] > 0.8

        result = rule_based_match("cowrie.command.input", "nmap -sV")
        assert result["confidence"] > 0.8
