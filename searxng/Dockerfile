# SearXNG with Scanrix's settings baked in (a bind mount of settings.yml fails on macOS when the
# repo lives in a privacy-protected folder like ~/Documents; copying it in works everywhere).
FROM searxng/searxng:2026.10.17-3afd94926
COPY settings.yml /etc/searxng/settings.yml
