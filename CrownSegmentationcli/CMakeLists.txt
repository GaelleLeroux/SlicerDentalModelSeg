#-----------------------------------------------------------------------------
set(MODULE_NAME CrownSegmentationcli)

SlicerMacroBuildScriptedCLI(
  NAME ${MODULE_NAME}
)

set(FOLDER_LIBRARY Dentalmodelseg)

set(MODULE_PYTHON_SCRIPTS
  ${FOLDER_LIBRARY}/__init__.py 
  )

  slicerMacroBuildScriptedModule(
    NAME  ${FOLDER_LIBRARY}
    SCRIPTS ${MODULE_PYTHON_SCRIPTS}
)