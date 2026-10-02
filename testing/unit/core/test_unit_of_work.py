from sqlalchemy.orm import Session

from memoria_curitibana.core.unit_of_work import UnitOfWork


def test_unit_of_work_delegates_to_session(mocker) -> None:
    db = mocker.Mock(spec=Session)
    uow = UnitOfWork(db)

    uow.commit()
    uow.rollback()
    uow.flush()

    db.commit.assert_called_once()
    db.rollback.assert_called_once()
    db.flush.assert_called_once()


def test_unit_of_work_transaction_uses_savepoint(mocker) -> None:
    db = mocker.Mock(spec=Session)
    savepoint = mocker.MagicMock()
    db.begin_nested.return_value = savepoint
    uow = UnitOfWork(db)

    with uow.transaction() as session:
        assert session is db

    db.begin_nested.assert_called_once()
    savepoint.__enter__.assert_called_once()
    savepoint.__exit__.assert_called_once()
