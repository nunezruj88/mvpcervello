import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from openpyxl import Workbook
import app
from importer import parse, ImportError, REQUIRED
from stats import summarize, playing_seconds

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'partido_ficticio.csv'

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.DB = Path(self.temp.name) / 'test.sqlite3'
        self.data = EXAMPLE.read_bytes()

    def tearDown(self): self.temp.cleanup()

    def call(self,path,method='GET',payload=None,origin=None,query=''):
        body=json.dumps(payload or {}).encode()
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':query,'HTTP_HOST':'localhost:8092',
             'wsgi.input':io.BytesIO(body),'CONTENT_LENGTH':str(len(body))}
        if origin: env['HTTP_ORIGIN']=origin
        response={}
        def start(status,headers): response.update(status=status,headers=dict(headers))
        response['body']=b''.join(app.application(env,start))
        if response['headers']['Content-Type'].startswith('application/json'): response['json']=json.loads(response['body'])
        return response

    def payload(self,**extra): return dict(filename=EXAMPLE.name,data=base64.b64encode(self.data).decode(),**extra)

    def test_example_and_focus(self):
        m=parse(EXAMPLE.name,self.data)
        self.assertEqual(len(m['events']),15)
        s=summarize([m])
        self.assertEqual(s['team']['points'],6)
        self.assertEqual(s['team']['fouls'],2)
        self.assertEqual(s['focus']['points'],2)
        self.assertEqual(s['focus']['made2'],1)
        self.assertEqual(len(s['focus_events']),1)
        self.assertEqual(s['partial'],1)
        self.assertIsNone(s['focus']['percent1'])

    def test_preview_duplicate_replace_and_persistence(self):
        self.assertEqual(self.call('/api/import','POST',self.payload(preview=True))['status'],'200 OK')
        self.assertEqual(len(app.matches()),0)
        self.assertEqual(self.call('/api/import','POST',self.payload())['status'],'201 Created')
        self.assertEqual(len(app.matches()),1)
        self.assertEqual(self.call('/api/import','POST',self.payload())['status'],'409 Conflict')
        self.assertEqual(self.call('/api/import','POST',self.payload(replace=True,complete=True))['status'],'201 Created')
        self.assertEqual(len(app.matches()),1)
        self.assertTrue(app.matches()[0]['complete'])
        self.assertEqual(self.call('/api/data')['json']['summary']['team']['points'],6)

    def test_invalid_import_preserves_previous(self):
        self.call('/api/import','POST',self.payload())
        payload=self.payload(replace=True)
        payload['data']=base64.b64encode(self.data.replace(b'Cistella de 2',b'Cistella de 3',1)).decode()
        self.assertEqual(self.call('/api/import','POST',payload)['status'],'400 Bad Request')
        self.assertEqual(summarize(app.matches())['team']['points'],6)

    def test_xlsx(self):
        import csv
        rows=list(csv.reader(io.StringIO(self.data.decode('utf-8-sig')),delimiter=';'))
        book=Workbook();sheet=book.active
        for row in rows: sheet.append(row)
        out=io.BytesIO();book.save(out)
        self.assertEqual(summarize([parse('test.xlsx',out.getvalue())])['focus']['points'],2)
        sheet['A2']='=1+1';out=io.BytesIO();book.save(out)
        with self.assertRaises(ImportError): parse('test.xlsx',out.getvalue())

    def test_no_other_team_12_in_focus(self):
        m=parse(EXAMPLE.name,self.data)
        m['events'].append(dict(m['events'][2],team='CB BEGUES',number=12,player='OTRO JUGADOR',points=2))
        self.assertEqual(summarize([m])['focus']['points'],2)

    def test_opponent_only_period(self):
        m=parse(EXAMPLE.name,self.data)
        m['events'].append(dict(m['events'][2],team='CB BEGUES',period='P9',points=3))
        m['events'].append(dict(m['events'][2],team='',period='P9',points=2))
        period=summarize([m])['periods'][-1]
        self.assertEqual(period['period'],'P9')
        self.assertEqual(period['team_points'],0)
        self.assertEqual(period['opponent_points'],3)

    def test_playing_time_excludes_p1_and_crosses_periods(self):
        m=parse(EXAMPLE.name,self.data)
        m['period_seconds']=360
        template=m['events'][2]
        def event(period,clock,action):
            return dict(template,team='MVP CERVELLÓ',player='M.N.L.',period=period,clock=clock,action=action,points=0)
        m['events']=[event('P1','06:00','Entra al camp'),event('P1','00:00','Surt del camp'),
                     event('P2','05:00','Entra al camp'),event('P2','03:00','Surt del camp'),
                     event('P2','01:00','Entra al camp'),event('P3','04:00','Surt del camp')]
        self.assertEqual(playing_seconds([m],'MVP CERVELLÓ','MNL'),300)
        self.assertEqual(playing_seconds([m,m],'MVP CERVELLÓ','MNL'),600)
        self.assertEqual(summarize([m])['players'][0]['playing_seconds'],300)
        m['events']=[event('P2','04:00','Surt del camp')]
        self.assertEqual(playing_seconds([m],'MVP CERVELLÓ','MNL'),120)
        m['events']=[event('P2','04:00','Entra al camp')]
        self.assertIsNone(playing_seconds([m],'MVP CERVELLÓ','MNL'))
        m['events'].append(event('P2','','Final de període'))
        self.assertEqual(playing_seconds([m],'MVP CERVELLÓ','MNL'),240)
        m['events']=[event('P2','04:00','Entra al camp'),event('P2','05:00','Surt del camp')]
        self.assertIsNone(playing_seconds([m],'MVP CERVELLÓ','MNL'))

    def test_export_roundtrip_and_origin(self):
        self.call('/api/import','POST',self.payload())
        exported=self.call('/api/export')['body']
        self.assertEqual(summarize([parse('export.csv',exported)])['team']['points'],6)
        result=self.call('/api/import','POST',self.payload(replace=True),origin='http://otro-host')
        self.assertEqual(result['status'],'403 Forbidden')

    def test_duration_from_first_row_and_legacy_data(self):
        header='Fecha_partido;Local;Visitante;Periodo;Tiempo_Restante;Equipo;Dorsal;Jugador;Accion_original;Puntos_accion\n'
        rows='2026-10-03;CB BEGUES;MVP CERVELLÓ;P1;10:00;MVP CERVELLÓ;12;M.N.L.;Entra al camp;0\n'
        rows+='2026-10-03;CB BEGUES;MVP CERVELLÓ;P2;10:00;MVP CERVELLÓ;12;M.N.L.;Entra al camp;0\n'
        rows+='2026-10-03;CB BEGUES;MVP CERVELLÓ;P2;07:00;MVP CERVELLÓ;12;M.N.L.;Surt del camp;0\n'
        self.data=(header+rows).encode()
        m=parse('duration.csv',self.data)
        self.assertEqual(m['period_seconds'],600)
        self.assertEqual(playing_seconds([m],'MVP CERVELLÓ','MNL'),180)
        del m['period_seconds']
        self.assertEqual(playing_seconds([m],'MVP CERVELLÓ','MNL'),180)
        self.assertEqual(self.call('/api/import','POST',self.payload())['status'],'201 Created')
        self.assertEqual(app.matches()[0]['period_seconds'],600)
        self.assertEqual(self.call('/api/data')['json']['summary']['players'][0]['playing_seconds'],180)
        import csv
        from datetime import time
        book=Workbook();sheet=book.active
        for row in csv.reader(io.StringIO(self.data.decode()),delimiter=';'): sheet.append(row)
        sheet['E2']=time(0,10,0)
        out=io.BytesIO();book.save(out)
        self.assertEqual(parse('duration.xlsx',out.getvalue())['period_seconds'],600)

    def test_bench_period_before_later_entries(self):
        m=parse(EXAMPLE.name,self.data)
        template=m['events'][2]
        def event(period,clock,action,player='JUGADOR PRUEBA'):
            return dict(template,team='MVP CERVELLÓ',player=player,period=period,clock=clock,action=action,points=0)
        m['period_seconds']=600
        m['events']=[event('P1','05:23','Entra al camp'),event('P1','01:27','Surt del camp'),
                     event('P2','','Final de període',player=''),
                     event('P3','05:41','Entra al camp'),event('P3','04:10','Surt del camp'),
                     event('P4','05:06','Entra al camp'),event('P4','','Final de període',player='')]
        self.assertEqual(playing_seconds([m],'MVP CERVELLÓ','JUGADORPRUEBA'),397)
        # A P1 entry can establish the P2 starter without counting any P1 time.
        m['events']=[event('P1','05:00','Entra al camp'),event('P2','08:00','Surt del camp')]
        self.assertEqual(playing_seconds([m],'MVP CERVELLÓ','JUGADORPRUEBA'),120)

if __name__=='__main__':unittest.main()
