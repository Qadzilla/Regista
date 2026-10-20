# Load KEY=VALUE lines from a .env file into the environment without executing it.
#
# `source .env` runs each line as shell: a value with ';' (the Application Insights connection string has three) is
# cut at the first ';' and the rest runs as commands. That silently deployed a connection string without its
# ingestion endpoint ("Exporter is missing a valid region") until 2026-10-20. This reader takes everything after the
# first '=' literally, strips one pair of surrounding quotes, skips comments and blank lines, and never overrides a
# variable already set in the environment (same rules as regista.cloud.config.load_dotenv).
#
#   . infra/lib/dotenv.sh && load_dotenv .env
load_dotenv() {
  local file="${1:-.env}" line key val
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"; key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    val="${line#*=}"; val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
    if [[ ${#val} -ge 2 && ( ( "${val:0:1}" == '"' && "${val: -1}" == '"' ) || ( "${val:0:1}" == "'" && "${val: -1}" == "'" ) ) ]]; then
      val="${val:1:${#val}-2}"
    fi
    [[ -n "${!key+x}" ]] && continue
    export "$key=$val"
  done < "$file"
}
