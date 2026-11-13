FROM ghcr.io/cua-lite/lite.osworld@sha256:2d51f12e1bff4a8621c3a810cd5399c2c678aafae0db310f757c8c240cf954b1

# The task agent and evaluator are mounted read-only at /task by OpenART.
# The framework overrides the image CMD with `tail -f /dev/null`; env/setup.sh
# starts the desktop supervisord stack instead.