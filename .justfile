default:
    echo "Use the .justfile for recurrent commands, or as a build system (even if it's not)."

set unstable
set script-interpreter := ['uv', 'run', '--script']

[script]
hello:
    # Add the [script] attribute to write scripts in Python, instead of bash.
    print("Hello from Python!")
