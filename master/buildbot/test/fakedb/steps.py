# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

from __future__ import annotations

import json

from twisted.internet import defer

from buildbot.db.steps import StepModel
from buildbot.db.steps import UrlModel
from buildbot.test.fakedb.base import FakeDBComponent
from buildbot.test.fakedb.row import Row
from buildbot.test.util import validation
from buildbot.util import epoch2datetime


class Step(Row):
    table = "steps"

    id_column = 'id'
    foreignKeys = ('buildid',)
    required_columns = ('buildid',)

    def __init__(
        self,
        id=None,
        number=29,
        name='step29',
        buildid=None,
        started_at=1304262222,
        locks_acquired_at=None,
        complete_at=None,
        state_string='',
        results=None,
        urls_json='[]',
        hidden=0,
    ):
        super().__init__(
            id=id,
            number=number,
            name=name,
            buildid=buildid,
            started_at=started_at,
            locks_acquired_at=locks_acquired_at,
            complete_at=complete_at,
            state_string=state_string,
            results=results,
            urls_json=urls_json,
            hidden=hidden,
        )


class FakeStepsComponent(FakeDBComponent):
    def setUp(self):
        self.steps = {}

    def insert_test_data(self, rows):
        for row in rows:
            if isinstance(row, Step):
                self.steps[row.id] = row.values.copy()

    # component methods

    def _newId(self):
        id = 100
        while id in self.steps:
            id += 1
        return id

    def _model_from_row(self, row):
        return StepModel(
            id=row['id'],
            buildid=row['buildid'],
            number=row['number'],
            name=row['name'],
            started_at=epoch2datetime(row['started_at']),
            locks_acquired_at=epoch2datetime(row["locks_acquired_at"]),
            complete_at=epoch2datetime(row['complete_at']),
            state_string=row['state_string'],
            results=row['results'],
            urls=[UrlModel(item['name'], item['url']) for item in json.loads(row['urls_json'])],
            hidden=bool(row['hidden']),
        )

    def getStep(
        self,
        stepid: int | None = None,
        buildid: int | None = None,
        number: int | None = None,
        name: str | None = None,
    ) -> defer.Deferred[StepModel | None]:
        if stepid is not None:
            row = self.steps.get(stepid)
            if not row:
                return defer.succeed(None)
            return defer.succeed(self._model_from_row(row))
        else:
            if number is None and name is None:
                return defer.fail(RuntimeError("specify both name and number"))
            for row in self.steps.values():
                if row['buildid'] != buildid:
                    continue
                if number is not None and row['number'] != number:
                    continue
                if name is not None and row['name'] != name:
                    continue
                return defer.succeed(self._model_from_row(row))
            return defer.succeed(None)

    def getSteps(self, buildid) -> defer.Deferred[list[StepModel]]:
        ret = []

        for row in self.steps.values():
            if row['buildid'] != buildid:
                continue
            ret.append(self._model_from_row(row))

        ret.sort(key=lambda r: r.number)
        return defer.succeed(ret)

    def addStep(self, buildid, name, state_string):
        validation.verifyType(self.t, 'state_string', state_string, validation.StringValidator())
        validation.verifyType(self.t, 'name', name, validation.IdentifierValidator(50))
        # get a unique name and number
        build_steps = [r for r in self.steps.values() if r['buildid'] == buildid]
        if build_steps:
            number = max(r['number'] for r in build_steps) + 1
            names = {r['name'] for r in build_steps}
            if name in names:
                i = 1
                while f'{name}_{i}' in names:
                    i += 1
                name = f'{name}_{i}'
        else:
            number = 0

        id = self._newId()
        self.steps[id] = {
            'id': id,
            'buildid': buildid,
            'number': number,
            'name': name,
            'started_at': None,
            "locks_acquired_at": None,
            'complete_at': None,
            'results': None,
            'state_string': state_string,
            'urls_json': '[]',
            'hidden': False,
        }

        return defer.succeed((id, number, name))

    def startStep(self, stepid, started_at, locks_acquired):
        b = self.steps.get(stepid)
        if b:
            b['started_at'] = started_at
            if locks_acquired:
                b["locks_acquired_at"] = started_at
        return defer.succeed(None)

    def set_step_locks_acquired_at(self, stepid, locks_acquired_at):
        b = self.steps.get(stepid)
        if b:
            b['locks_acquired_at'] = locks_acquired_at
        return defer.succeed(None)

    def setStepStateString(self, stepid, state_string):
        validation.verifyType(self.t, 'state_string', state_string, validation.StringValidator())
        b = self.steps.get(stepid)
        if b:
            b['state_string'] = state_string
        return defer.succeed(None)

    def addURL(self, stepid, name, url, _racehook=None):
        validation.verifyType(self.t, 'stepid', stepid, validation.IntValidator())
        validation.verifyType(self.t, 'name', name, validation.IdentifierValidator(50))
        validation.verifyType(self.t, 'url', url, validation.StringValidator())
        b = self.steps.get(stepid)
        if b:
            urls = json.loads(b['urls_json'])
            url_item = {"name": name, "url": url}
            if url_item not in urls:
                urls.append(url_item)
            b['urls_json'] = json.dumps(urls)
        return defer.succeed(None)

    def finishStep(self, stepid, results, hidden):
        now = self.reactor.seconds()
        b = self.steps.get(stepid)
        if b:
            b['complete_at'] = now
            b['results'] = results
            b['hidden'] = bool(hidden)
        return defer.succeed(None)
