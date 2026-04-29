#!/bin/sh
set -eu

find_nss_wrapper() {
  for candidate in /usr/lib/*/libnss_wrapper.so /lib/*/libnss_wrapper.so; do
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

setup_user() {
  uid="$(id -u)"
  gid="$(id -g)"
  home_dir="${HOME:-/tmp}"
  passwd_file="$home_dir/.nss-passwd"
  group_file="$home_dir/.nss-group"

  mkdir -p "$home_dir"
  export USER="${USER:-codex}"
  export LOGNAME="${LOGNAME:-$USER}"

  if grep -Eq "^[^:]*:[^:]*:${uid}:" /etc/passwd; then
    return 0
  fi

  cp /etc/passwd "$passwd_file"
  cp /etc/group "$group_file"

  if ! grep -Eq "^[^:]*:[^:]*:${gid}:" "$group_file"; then
    printf '%s:x:%s:\n' "$USER" "$gid" >> "$group_file"
  fi

  printf '%s:x:%s:%s:Codex Container User:%s:/bin/sh\n' "$USER" "$uid" "$gid" "$home_dir" >> "$passwd_file"

  nss_wrapper_lib="$(find_nss_wrapper || true)"
  if [ -n "$nss_wrapper_lib" ]; then
    export NSS_WRAPPER_PASSWD="$passwd_file"
    export NSS_WRAPPER_GROUP="$group_file"
    if [ -n "${LD_PRELOAD:-}" ]; then
      export LD_PRELOAD="$nss_wrapper_lib:$LD_PRELOAD"
    else
      export LD_PRELOAD="$nss_wrapper_lib"
    fi
  fi
}

setup_user
exec "$@"
