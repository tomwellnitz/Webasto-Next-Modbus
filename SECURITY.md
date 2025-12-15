# Security Policy

## Supported Versions

We actively maintain and provide security updates for the following versions:

| Version | Supported |
| ------- | ------------------ |
| 1.1.x | :white_check_mark: |
| 1.0.x | :white_check_mark: |
| < 1.0 | :x: |

## Reporting a Vulnerability

We take the security of Webasto Next seriously. If you discover a security vulnerability, please follow these steps:

### How to Report

1. **Do NOT open a public GitHub issue** for security vulnerabilities.
1. Instead, report security issues privately by:
   - Opening a [Security Advisory](https://github.com/tomwellnitz/Webasto-Next-Modbus/security/advisories/new) on GitHub (preferred)
   - Or sending an email to the maintainer via GitHub (if advisories are unavailable)

### What to Include

Please provide as much information as possible:

- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact and severity assessment
- Any suggested fixes or mitigations
- Your contact information for follow-up

### What to Expect

- **Acknowledgment**: We will acknowledge receipt of your report within 48 hours.
- **Investigation**: We will investigate and validate the vulnerability within 5 business days.
- **Updates**: We will keep you informed of our progress throughout the resolution process.
- **Resolution**: We aim to release a patch within 30 days for confirmed vulnerabilities.
- **Credit**: With your permission, we will publicly credit you for the discovery once the vulnerability is resolved.

## Security Best Practices

When using this integration:

### Network Security

- **Local Network Only**: This integration communicates with wallboxes over your local network. Ensure your network is properly secured.
- **Firewall**: Consider restricting Modbus TCP (port 502) and REST API access (port 80) to trusted devices only.
- **No Internet Exposure**: Never expose your wallbox directly to the internet without proper security measures.

### Credentials

- **REST API Credentials**: If you enable REST API features, credentials are stored securely in Home Assistant's encrypted storage.
- **Strong Passwords**: Use strong, unique passwords for your wallbox web interface.
- **Default Credentials**: Change default credentials (username: `admin`) immediately after installation.

### Updates

- **Keep Updated**: Always use the latest version of this integration to receive security patches.
- **Wallbox Firmware**: Keep your wallbox firmware updated according to manufacturer recommendations.
- **Home Assistant**: Keep your Home Assistant installation updated.

## Known Security Considerations

### Modbus TCP

- Modbus TCP protocol does not include built-in authentication or encryption.
- Communication occurs in plaintext over your local network.
- Only deploy in trusted network environments.

### REST API

- REST API credentials are transmitted over HTTP (not HTTPS by default on most wallboxes).
- Use secure network practices (e.g., dedicated VLAN for IoT devices).

### Life Bit Mechanism

- The integration sends periodic "keep-alive" signals (Life Bit) to maintain wallbox responsiveness.
- This is a safety feature implemented by the wallbox manufacturer.
- Failure to send Life Bit signals triggers the wallbox fail-safe mechanism.

## Scope

This security policy covers:

- The Home Assistant custom component code in this repository
- The virtual wallbox simulator (for development/testing only)
- Integration-specific configuration and data handling

**Out of Scope:**

- Vulnerabilities in the wallbox hardware or firmware (report to Webasto/Ampure)
- Home Assistant core vulnerabilities (report to Home Assistant project)
- Third-party dependencies (report to respective maintainers)

## Security Updates

Security updates are announced via:

- GitHub Security Advisories
- Release notes in `CHANGELOG.md`
- GitHub Releases with appropriate tags

## Questions

For questions about this security policy, open a discussion in the [GitHub Discussions](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions) board or contact the maintainer.
