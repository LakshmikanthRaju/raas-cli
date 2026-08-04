# Simple test state - no Jinja, no dependencies
test_file:
  file.managed:
    - name: /tmp/salt-test.txt
    - contents: "Hello from Salt"
