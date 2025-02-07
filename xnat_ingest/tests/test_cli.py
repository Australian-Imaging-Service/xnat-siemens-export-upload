import os
import shutil
from datetime import datetime
from pathlib import Path
from frametree.core.cli import (  # type: ignore[import-untyped]
    define as dataset_define,
    add_source as dataset_add_source,
)
import xnat4tests  # type: ignore[import-untyped]
from frametree.core.cli.store import add as store_add  # type: ignore[import-untyped]
from xnat_ingest.cli import stage, upload
from xnat_ingest.cli.stage import STAGED_NAME_DEFAULT
from xnat_ingest.utils import show_cli_trace
from fileformats.medimage import DicomSeries
from medimages4tests.dummy.dicom.pet.wholebody.siemens.biograph_vision.vr20b import (  # type: ignore[import-untyped]
    get_image as get_pet_image,
)
from medimages4tests.dummy.dicom.ct.ac.siemens.biograph_vision.vr20b import (  # type: ignore[import-untyped]
    get_image as get_ac_image,
)
from medimages4tests.dummy.dicom.pet.topogram.siemens.biograph_vision.vr20b import (  # type: ignore[import-untyped]
    get_image as get_topogram_image,
)
from medimages4tests.dummy.dicom.pet.statistics.siemens.biograph_vision.vr20b import (  # type: ignore[import-untyped]
    get_image as get_statistics_image,
)
from conftest import get_raw_data_files


PATTERN = "{PatientName.family_name}_{PatientName.given_name}_{SeriesDate}.*"


def test_stage_and_upload(
    xnat_project,
    xnat_config,
    xnat_server,
    cli_runner,
    run_prefix,
    tmp_path: Path,
    tmp_gen_dir: Path,
):
    # Get test image data

    dicoms_dir = tmp_path / "dicoms"
    dicoms_dir.mkdir(exist_ok=True)

    associated_files_dir = tmp_path / "non-dicoms"
    associated_files_dir.mkdir(exist_ok=True)

    staging_dir = tmp_path / "staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir()

    log_file = tmp_path / "logging.log"
    if log_file.exists():
        os.unlink(log_file)

    # Delete any existing sessions from previous test runs
    session_ids = []
    with xnat4tests.connect() as xnat_login:
        for i, c in enumerate("abc"):
            first_name = f"First{c.upper()}"
            last_name = f"Last{c.upper()}"
            PatientID = f"subject{i}"
            AccessionNumber = f"98765432{i}"
            session_ids.append(f"{PatientID}_{AccessionNumber}")

            StudyInstanceUID = (
                f"1.3.12.2.1107.5.1.4.10016.3000002308242209356530000001{i}"
            )

            series = DicomSeries(
                get_pet_image(
                    tmp_gen_dir / f"pet{i}",
                    first_name=first_name,
                    last_name=last_name,
                    StudyInstanceUID=StudyInstanceUID,
                    PatientID=PatientID,
                    AccessionNumber=AccessionNumber,
                    StudyID=xnat_project,
                ).iterdir()
            )
            for dcm in series.contents:
                os.link(dcm, dicoms_dir / f"pet{i}-{dcm.fspath.name}")
            series = DicomSeries(
                get_ac_image(
                    tmp_gen_dir / f"ac{i}",
                    first_name=first_name,
                    last_name=last_name,
                    StudyInstanceUID=StudyInstanceUID,
                    PatientID=PatientID,
                    AccessionNumber=AccessionNumber,
                    StudyID=xnat_project,
                ).iterdir()
            )
            for dcm in series.contents:
                os.link(dcm, dicoms_dir / f"ac{i}-{dcm.fspath.name}")
            series = DicomSeries(
                get_topogram_image(
                    tmp_gen_dir / f"topogram{i}",
                    first_name=first_name,
                    last_name=last_name,
                    StudyInstanceUID=StudyInstanceUID,
                    PatientID=PatientID,
                    AccessionNumber=AccessionNumber,
                    StudyID=xnat_project,
                ).iterdir()
            )
            for dcm in series.contents:
                os.link(dcm, dicoms_dir / f"topogram{i}-{dcm.fspath.name}")
            series = DicomSeries(
                get_statistics_image(
                    tmp_gen_dir / f"statistics{i}",
                    first_name=first_name,
                    last_name=last_name,
                    StudyInstanceUID=StudyInstanceUID,
                    PatientID=PatientID,
                    AccessionNumber=AccessionNumber,
                    StudyID=xnat_project,
                ).iterdir()
            )
            for dcm in series.contents:
                os.link(dcm, dicoms_dir / f"statistics{i}-{dcm.fspath.name}")
            assoc_fspaths = get_raw_data_files(
                tmp_gen_dir / f"non-dicom{i}",
                first_name=first_name,
                last_name=last_name,
                date_time=datetime(2023, 8, 25, 15, 50, 5, i),
            )
            for assoc_fspath in assoc_fspaths:
                os.link(
                    assoc_fspath,
                    associated_files_dir
                    / f"{assoc_fspath.stem}-{i}{assoc_fspath.suffix}",
                )

    # Create data store
    result = cli_runner(
        store_add,
        [
            "xnat",
            "testxnat",
            "--server",
            xnat_server,
            "--user",
            xnat_config.xnat_user,
            "--password",
            xnat_config.xnat_password,
        ],
    )
    assert result.exit_code == 0, show_cli_trace(result)

    dataset_locator = f"testxnat//{xnat_project}"

    # Create dataset definition
    result = cli_runner(dataset_define, [dataset_locator])
    assert result.exit_code == 0, show_cli_trace(result)

    for col_name, col_type, col_pattern in [
        ("pet", "medimage/dicom-series", "PET SWB 8MIN"),
        ("topogram", "medimage/dicom-series", "Topogram.*"),
        ("atten_corr", "medimage/dicom-series", "AC CT.*"),
        (
            "listmode",
            "medimage/vnd.siemens.biograph128-vision.vr20b.pet-list-mode",
            ".*/LISTMODE",
        ),
        # (
        #     "sinogram",
        #     "medimage/vnd.siemens.biograph128-vision.vr20b.pet-sinogram",
        #     ".*/EM_SINO",
        # ),
        (
            "countrate",
            "medimage/vnd.siemens.biograph128-vision.vr20b.pet-count-rate",
            ".*/COUNTRATE",
        ),
    ]:
        # Add dataset columns
        result = cli_runner(
            dataset_add_source,
            [
                dataset_locator,
                col_name,
                col_type,
                "--path",
                col_pattern,
            ],
        )
        assert result.exit_code == 0, show_cli_trace(result)

    result = cli_runner(
        stage,
        [
            str(dicoms_dir),
            str(staging_dir),
            "--associated-files",
            "medimage/vnd.siemens.biograph128-vision.vr20b.pet-raw-data",
            str(associated_files_dir)
            + "/{PatientName.family_name}_{PatientName.given_name}*.ptd",
            r".*/[^\.]+.[^\.]+.[^\.]+.(?P<id>\d+)\.[A-Z]+_(?P<resource>[^\.]+).*",
            # "--logger",
            # "file",
            # "info",
            # str(log_file),
            "--additional-logger",
            "xnat",
            "--raise-errors",
            "--delete",
            "--xnat-login",
            "http://localhost:8080",
            "admin",
            "admin",
        ],
        env={
            "XINGEST_LOGGERS": "file,info,/tmp/logging.log;stream,debug,stdout",
        },
    )

    assert result.exit_code == 0, show_cli_trace(result)

    result = cli_runner(
        upload,
        [
            str(staging_dir / STAGED_NAME_DEFAULT),
            "--logger",
            "file",
            "info",
            str(log_file),
            "--additional-logger",
            "xnat",
            "--always-include",
            "medimage/dicom-series",
            "--raise-errors",
            "--method",
            "tar_file",
            "--use-curl-jsession",
            "--wait-period",
            "0",
        ],
        env={
            "XINGEST_HOST": xnat_server,
            "XINGEST_USER": "admin",
            "XINGEST_PASS": "admin",
        },
    )

    assert result.exit_code == 0, show_cli_trace(result)

    with xnat4tests.connect() as xnat_login:
        xproject = xnat_login.projects[xnat_project]
        for session_id in session_ids:
            xsession = xproject.experiments[session_id]
            scan_ids = sorted(xsession.scans)

            assert scan_ids == [
                "1",
                "2",
                "4",
                "6",
                "602",
                # "603",
            ]
