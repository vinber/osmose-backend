#!/usr/bin/env python
#-*- coding: utf-8 -*-

###########################################################################
##                                                                       ##
## Copyrights Etienne Chové <chove@crans.org> 2009                       ##
## Copyrights Frédéric Rodrigo 2011-2015                                 ##
##                                                                       ##
## This program is free software: you can redistribute it and/or modify  ##
## it under the terms of the GNU General Public License as published by  ##
## the Free Software Foundation, either version 3 of the License, or     ##
## (at your option) any later version.                                   ##
##                                                                       ##
## This program is distributed in the hope that it will be useful,       ##
## but WITHOUT ANY WARRANTY; without even the implied warranty of        ##
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         ##
## GNU General Public License for more details.                          ##
##                                                                       ##
## You should have received a copy of the GNU General Public License     ##
## along with this program.  If not, see <http://www.gnu.org/licenses/>. ##
##                                                                       ##
###########################################################################

from Analyser_Osmosis import Analyser_Osmosis

sql10 = """
CREATE TEMP TABLE buildings AS
SELECT
    ways.id,
    ways.linestring,
    ways.tags->'building' AS building,
    NOT ways.tags?'wall' OR ways.tags->'wall' != 'no' AS wall,
    array_length(ways.nodes, 1) AS nodes_length,
    ST_MakePolygon(ways.linestring) AS polygon
FROM
    ways
    LEFT JOIN relation_members ON
        relation_members.member_id = ways.id AND
        relation_members.member_type = 'W'
WHERE
    relation_members.member_id IS NULL AND
    ways.tags != ''::hstore AND
    ways.tags?'building' AND
    ways.tags->'building' != 'no' AND
    NOT ways.tags?'layer' AND
    is_polygon AND
    ST_IsValid(ways.linestring) = 't' AND
    ST_IsSimple(ways.linestring) = 't'
"""

sql11 = """
CREATE INDEX buildings_polygon_idx ON buildings USING gist(polygon)
"""

sql12 = """
CREATE INDEX buildings_wall_idx ON buildings(wall)
"""

sql20 = """
CREATE TEMP TABLE bnodes AS
SELECT
    id,
    ST_PointN(linestring, generate_series(1, ST_NPoints(linestring))) AS geom
FROM
    buildings
WHERE
    wall
"""

sql21 = """
CREATE INDEX bnodes_geom ON bnodes USING GIST(geom);
"""

sql30 = """
CREATE TABLE intersection_{0}_{1} AS
SELECT
    b1.id AS id1,
    b2.id AS id2,
    ST_AsText(ST_Centroid(ST_Intersection(b1.polygon, b2.polygon))),
    ST_Area(ST_Intersection(b1.polygon, b2.polygon)) AS intersectionArea,
    least(ST_Area(b1.polygon), ST_Area(b2.polygon))*0.10 AS threshold,
    b1.linestring AS linestring1
FROM
    {0}buildings AS b1,
    {1}buildings AS b2
WHERE
    b1.id > b2.id AND
    b1.wall AND
    b2.wall AND
    b1.polygon && b2.polygon AND
    ST_Area(ST_Intersection(b1.polygon, b2.polygon)) <> 0
"""

sql31 = """
SELECT
    *
FROM
    intersection_{0}_{1}
"""

sql40 = """
SELECT
    id,
    ST_AsText(ST_Centroid(polygon))
FROM
    {0}buildings
WHERE
    wall AND
    ST_Area(polygon) < 0.05e-10
"""

sql50 = """
SELECT
    DISTINCT ON (bnodes.id, bnodes.geom)
    buildings.id,
    bnodes.id,
    ST_AsText(bnodes.geom)
FROM
    {0}buildings AS buildings
    JOIN {1}bnodes AS bnodes ON
        buildings.id > bnodes.id AND
        ST_DWithin(buildings.linestring, bnodes.geom, 1e-7) AND
        ST_Disjoint(buildings.linestring, bnodes.geom)
WHERE
    buildings.wall
ORDER BY
    bnodes.id,
    bnodes.geom
"""

sql60 = """
SELECT
    ST_AsText(ST_Centroid(geom)),
    ST_Area(geom)
FROM
    (
    SELECT
        (ST_Dump(ST_Union(ST_Buffer(linestring1, 5e-3, 'quad_segs=2')))).geom AS geom
    FROM
        intersection_{0}_{1}
    WHERE
        intersectionArea > threshold
    ) AS buffer
WHERE
    ST_Area(geom) > 5e-4
"""

sql70 = """
SELECT
   DISTINCT ON (b2.id)
   b2.id,
   ST_AsText(way_locate(b2.linestring))
FROM
   {0}buildings AS b1,
   {1}buildings AS b2
WHERE
   b2.nodes_length = 4 AND
   b2.id != b1.id AND
   b1.building = b2.building AND
   b1.wall = b2.wall AND
   ST_Intersects(b1.polygon, b2.polygon)
"""

class Analyser_Osmosis_Building_Overlaps(Analyser_Osmosis):

    def __init__(self, config, logger = None):
        Analyser_Osmosis.__init__(self, config, logger)
        self.FR = config.options and ("country" in config.options and config.options["country"] == "FR" or "test" in config.options)
        self.classs_change[1] = {"item":"0", "level": 3, "tag": ["building", "geom", "fix:chair"], "desc": T_(u"Building intersection") }
        self.classs_change[2] = {"item":"0", "level": 2, "tag": ["building", "geom", "fix:chair"], "desc": T_(u"Large building intersection") }
        self.classs_change[3] = {"item":"0", "level": 3, "tag": ["building", "geom", "fix:chair"], "desc": T_(u"Building too small") }
        self.classs_change[4] = {"item":"0", "level": 3, "tag": ["building", "geom", "fix:chair"], "desc": T_(u"Gap between buildings") }
        self.classs_change[5] = {"item":"0", "level": 1, "tag": ["building", "fix:chair"], "desc": T_(u"Large building intersection cluster") }
        if self.FR:
            self.classs_change[6] = {"item":"1", "level": 3, "tag": ["building", "geom", "fix:chair"], "desc": T_(u"Building in parts") }
        self.callback30 = lambda res: {"class":2 if res[3]>res[4] else 1, "data":[self.way, self.way, self.positionAsText]}
        self.callback40 = lambda res: {"class":3, "data":[self.way, self.positionAsText]}
        self.callback50 = lambda res: {"class":4, "data":[self.way, self.way, self.positionAsText]}
        self.callback60 = lambda res: {"class":5, "data":[self.positionAsText]}
        if self.FR:
            self.callback70 = lambda res: {"class":6, "data":[self.way, self.positionAsText]}

    def analyser_osmosis_full(self):
        self.run(sql10)
        self.run(sql11)
        self.run(sql12)
        self.run(sql20)
        self.run(sql21)
        self.run(sql30.format("", ""))
        self.run(sql31.format("", ""), self.callback30)
        self.run(sql40.format(""), self.callback40)
        self.run(sql50.format("", ""), self.callback50)
        self.run(sql60.format("", ""), self.callback60)
        if self.FR:
            self.run(sql70.format("", ""), self.callback70)

    def analyser_osmosis_diff(self):
        self.run(sql10)
        self.run(sql11)
        self.run(sql12)
        self.run(sql20)
        self.run(sql21)
        self.create_view_touched("buildings", "W")
        self.create_view_touched("bnodes", "W")
        self.create_view_not_touched('buildings', 'W')
        self.run(sql30.format("touched_", ""))
        self.run(sql30.format("not_touched_", "touched_"))
        self.run(sql31.format("touched_", ""), self.callback30)
        self.run(sql31.format("not_touched_", "touched_"), self.callback30)
        self.run(sql40.format("touched_"), self.callback40)
        self.run(sql50.format("touched_", ""), self.callback50)
        self.run(sql50.format("not_touched_", "touched_"), self.callback50)
        #self.run(sql60.format("", ""), self.callback60) Can be done in diff mode without runing a full sql30
        if self.FR:
            self.run(sql70.format("touched_", ""), self.callback70)
            self.run(sql70.format("not_touched_", "touched_"), self.callback70)
