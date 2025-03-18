{
  lib,
  buildPythonPackage,
  setuptools,

  sfconn,
  snowflake-snowpark-python,
  make4db-api,
  yappt,
}:
buildPythonPackage {
  pname = "make4db-snowflake";
  version = "0.1.2";
  pyproject = true;

  src = ./.;

  dependencies = [
    sfconn
    snowflake-snowpark-python
    make4db-api
    yappt
  ];

  nativeBuildInputs = [ setuptools ];
  doCheck = false;

  meta = with lib; {
    description = "make4db provider for Snowflake";
    maintainers = with maintainers; [ padhia ];
  };
}
