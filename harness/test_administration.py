"""Unit checks for stage isolation using synthetic administrator state only."""
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from pilot import APP, RUN, Session, Trace, inventory, sha
from operator_api import pointer, resolve


class AdministrationTests(unittest.TestCase):
    def state(self,directory,sid,stages):
        # No candidate application is launched and no real scenario attempt is
        # created. Boundary markers here are synthetic tool fixtures only.
        session=Session.__new__(Session)
        session.sid=sid;session.smoke=False;session.entry={'stages':stages}
        session.directory=directory;session.input=directory/'input';session.input.mkdir()
        session.data=directory/'data';session.data.mkdir();session.database=session.data/'unchanged.db'
        db=sqlite3.connect(session.database)
        db.execute('CREATE TABLE synthetic_state(value TEXT)');db.execute('INSERT INTO synthetic_state VALUES(?)',('pre-existing history must survive',));db.commit();db.close()
        session.stage=1;session.completed=[];session.acknowledged=True;session.boundary=False
        session.sealed=False;session.invalid=False;session.pausing=False;session.lock=threading.RLock()
        session.trace=Trace(directory/'observations')
        return session

    def test_declared_stage_delivery_preserves_existing_state(self):
        for sid in ['B002','B012','B019']:
            with tempfile.TemporaryDirectory(dir=RUN/'readiness',prefix='synthetic-stage-') as name:
                session=self.state(Path(name),sid,2)
                before=sha(session.database)
                with self.assertRaises(ValueError):session.control({'action':'deliver-next'})
                self.assertFalse((session.input/'stage-2').exists())
                session.boundary=True;session.completed=[1]
                result=session.control({'action':'deliver-next'})
                self.assertEqual(result['stage'],2)
                self.assertEqual(sha(session.database),before)
                self.assertEqual(set(inventory(session.input/'stage-2')),{'submission-contract.md','event.json','event.md'})
                event=json.loads((session.input/'stage-2/event.json').read_text())
                self.assertEqual(event['scenario_id'],sid)
                self.assertEqual(event['stage'],2)
                self.assertFalse(session.boundary)
                with self.assertRaises(ValueError):session.control({'action':'deliver-next'})
                self.assertEqual(session.completed,[1])

    def test_cannot_seal_missing_declared_stage(self):
        with tempfile.TemporaryDirectory(dir=RUN/'readiness',prefix='synthetic-seal-') as name:
            session=self.state(Path(name),'B002',2)
            session.boundary=True;session.completed=[1]
            with self.assertRaises(ValueError):session.control({'action':'seal'})

    def test_undeclared_stage_refused(self):
        with tempfile.TemporaryDirectory(dir=RUN/'readiness',prefix='synthetic-undeclared-') as name:
            session=self.state(Path(name),'B001',1)
            session.boundary=True;session.completed=[1]
            with self.assertRaises(ValueError):session.control({'action':'deliver-next'})

    def test_action_plan_uses_observed_response_only(self):
        self.assertEqual(resolve({'id':{'$response':'actual','pointer':'/id'}},{'actual':{'id':17}}),{'id':17})
        self.assertEqual(pointer({'a/b':[1,2]},'/a~1b/1'),2)
        with self.assertRaises(KeyError):resolve({'$response':'invented','pointer':'/id'}, {})


if __name__=='__main__':unittest.main()
