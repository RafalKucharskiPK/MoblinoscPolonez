import win32com.client
import os
import pandas as pd
__WBR__ = True

VISUM_PATH = os.path.join(os.getcwd(),"data//visum.ver")
#VISUM_PATH = "E://PAN//WBR.ver"
ATTS = ["LENGTH",	"IMPEDANCE",	"T0",	"TCUR",	"V0",	"VCUR"]
ATT = "TCUR"
ATT_PUT = "Time"


TSYS = "SO"
MODE = "KZ"
DEP_TIME = "16:00"
KRYTERIUM = 1
MATRIX_NO = 102

BUDGET = 120

CZAS_PARKOWANIA = {"SPPN":6*60,
                   "POZA_SPPN":3*60}


POI_CAT = 1
#POI_CAT = 37 # stadiony - 10 obiektow
"""
Attributes for SPS PrT
Member                  Value
criteria_AddVal1        4  
criteria_AddVal2        5  
criteria_AddVal3        6 
criteria_Distance       3 
criteria_Impedance      2  
criteria_t0             0 
criteria_tCur           1 
PrTSearchCriterionT_End 7   
"""


"""
Attributes for SPS PuT
Arr  
ArrDay  
ArrTime  
Dep  
DepDay  
DepTime  
OrigZoneNo  
DestZoneNo  
FromStopAreaNo  
ToStopAreaNo  
FromNodeNo  
ToNodeNo  
Length  
Time 
"""
def SPS_PrT(_from, _to, _tsys = TSYS):
    # Szuka sciezki w sieci drogowej dla zadanego kryterium pomiedzy zadana para punktow, zwraca zadany atrybut
    RouteSearch = Visum.Analysis.RouteSearchPrT
    Route = Visum.CreateNetElements()
    RouteSearch.Clear()
    Route.Add(_from)
    Route.Add(_to)
    RouteSearch.Execute(Route, _tsys, KRYTERIUM)
    return RouteSearch.AttValue(ATT)

def SPS_PuT(_from, _to):
    # Szuka sciezki w sieci KZ dla zadanego kryterium pomiedzy zadana para punktow, zwraca zadany atrybut
    RouteSearch = Visum.Analysis.RouteSearchPuT
    Route = Visum.CreateNetElements()
    RouteSearch.Clear()
    Route.Add(_from)
    Route.Add(_to)
    RouteSearch.Execute(Route,MODE, DEP_TIME)
    return RouteSearch.AttValue(ATT_PUT)

def POI2NearestNode(Visum):
    Visum.Graphic.StopDrawing = True
    mm = Visum.Net.CreateMapMatcher()
    Iterator = Visum.Net.POICategories.ItemByKey(POI_CAT).POIs.Iterator
    while Iterator.Valid:
        POI = Iterator.Item
        nearest_node = mm.GetNearestNode(POI.AttValue("XCoord"), POI.AttValue("YCoord"), 500, False)
        if nearest_node.Success:
            POI.SetAttValue("Node", nearest_node.Node.AttValue("No"))
            POI.SetAttValue("Dist_PrT", nearest_node.Distance/1.4)
        Iterator.Next()
    Visum.Graphic.StopDrawing = False

def POI2NearestSPoint(Visum):
    Visum.Graphic.StopDrawing = True
    mm = Visum.Net.CreateMapMatcher()
    Iterator = Visum.Net.POICategories.ItemByKey(POI_CAT).POIs.Iterator
    while Iterator.Valid:
        POI = Iterator.Item
        nearest_node = mm.GetNearestNode(POI.AttValue("XCoord"), POI.AttValue("YCoord"), 1000, True)
        if nearest_node.Success:
            if nearest_node.Node.AttValue(r"COUNT:STOPAREAS") < 2:
                POI.SetAttValue("SPoint", nearest_node.Node.AttValue(r"CONCATENATE:STOPAREAS\NO"))
            else:
                POI.SetAttValue("SPoint", nearest_node.Node.AttValue(r"CONCATENATE:STOPAREAS\NO").split(",")[0])
            POI.SetAttValue("Dist_PuT", nearest_node.Distance/1.4)
        Iterator.Next()
    Visum.Graphic.StopDrawing = False


def POI2NearestZone(Visum):
    Visum.Graphic.StopDrawing = True
    mm = Visum.Net.CreateMapMatcher()
    Iterator = Visum.Net.POICategories.ItemByKey(POI_CAT).POIs.Iterator
    while Iterator.Valid:
        POI = Iterator.Item
        Z = Visum.Net.Zones.ItemByKey(POI.AttValue("ZoneID"))  # para rejonow Z
        nearest_node = mm.GetNearestNode(POI.AttValue("XCoord"), POI.AttValue("YCoord"), 500, False)
        if nearest_node.Success:
            POI.SetAttValue("Node", nearest_node.Node.AttValue("No"))
            CzPrT = SPS_PrT(Z, nearest_node.Node)
            POI.SetAttValue("Czas_Zone", CzPrT + nearest_node.Distance / 1.4)
        Iterator.Next()

    Visum.Graphic.StopDrawing = False

def MainLoopStages(Visum):
    Visum.Graphic.StopDrawing = True  # nie rysuj (przyspieszenie)
    # inicjalizacja bazy dancyh (do csv)
    df_s1 = pd.DataFrame(columns=["Z_Rejon", "POI", "Czas_PrT", "Czas_PuT"])
    df_s2 = pd.DataFrame(columns=["POI", "Do_Rejon", "Czas_PrT", "Czas_PuT"])

    Zones = Visum.Net.Zones.GetMultiAttValues("No")  # rejony do iteracji
    # dane o POI
    POIs = Visum.Net.POICategories.ItemByKey(POI_CAT).POIs.GetMultipleAttributes(["No", "Node", "SPoint", "Dist_PrT", "Dist_PuT"])

    # glowna petla
    for OZone in Zones[:30]:
        Z = Visum.Net.Zones.ItemByKey(OZone[1]) # para rejonow Z
        for POI in POIs:
            #s1
            Przez_PrT = Visum.Net.Nodes.ItemByKey(POI[1]) #Punkt w sieci dla POI
            CzPrT = SPS_PrT(Z, Przez_PrT) \
                    + POI[3] +\
                    (CZAS_PARKOWANIA["SPPN"] if Z.AtrValue("F_SPPN")>0 else CZAS_PARKOWANIA["POZA_SPPN"]) # Oblicz czas PrT (2x dojscie do POI)

            if POI[2] is not None:
                Przez_PuT = Visum.Net.StopAreas.ItemByKey(POI[2]) # Przystanek dla POI (jesli jest)
                CzPuT = SPS_PuT(Z, Przez_PuT) + POI[4]   # Oblicz czas PuT (2x dojscie do POI)
            else:
                CzPuT = 999999
            print("From Zone {} to POI {} in {} PrT, {} PuT".format(OZone[1], int(POI[0]), CzPrT, CzPuT))
            df_s1.loc[df_s1.shape[0] + 1] = [OZone[1], int(POI[0]), CzPrT, CzPuT] # zapisz rekord w bazie danych

            #s2
            CzPrT = SPS_PrT(Przez_PrT, Z) + POI[3]  # Oblicz czas PrT (2x dojscie do POI)

            if POI[2] is not None:
                Przez_PuT = Visum.Net.StopAreas.ItemByKey(POI[2])  # Przystanek dla POI (jesli jest)
                CzPuT = SPS_PuT(Przez_PuT,Z) + POI[4]  # Oblicz czas PuT (2x dojscie do POI)
            else:
                CzPuT = 999999
            print("From POI {} to Zone {} in {} PrT, {} PuT".format(int(POI[0]), OZone[1] , CzPrT, CzPuT))
            df_s2.loc[df_s1.shape[0] + 1] = [int(POI[0]), OZone[1], CzPrT, CzPuT]  # zapisz rekord w bazie danych

    df_s1.to_csv("data//From_Via.csv")  # zapisz baze do pliku
    df_s2.to_csv("data//Via_To.csv")  # zapisz baze do pliku
    Visum.Graphic.StopDrawing = False


def MainLoop(Visum):
    Visum.Graphic.StopDrawing = True  # nie rysuj (przyspieszenie)
    # inicjalizacja bazy dancyh (do csv)
    df = pd.DataFrame(columns=["Z_Rejon", "Do_Rejon", "L_Podrozy", "Przez_POI", "Czas_PrT", "Czas_PuT"])

    Zones = Visum.Net.Zones.GetMultiAttValues("No")  # rejony do iteracji
    # dane o POI
    POIs = Visum.Net.POICategories.ItemByKey(POI_CAT).POIs.GetMultipleAttributes(["No", "Node", "SPoint", "Dist_PrT", "Dist_PuT"])

    # glowna petla
    for OZone in Zones:
        for DZone in Zones:
            if OZone != DZone:
                nTrips = Visum.Net.Matrices.ItemByKey(MATRIX_NO).GetValue(OZone[1],DZone[1]) # liczba podrozy (z macierzy)
                Z = Visum.Net.Zones.ItemByKey(OZone[1]) # para rejonow Z
                Do = Visum.Net.Zones.ItemByKey(DZone[1]) # i do
                for POI in POIs:
                    Przez_PrT = Visum.Net.Nodes.ItemByKey(POI[1]) #Punkt w sieci dla POI
                    CzPrT = SPS_PrT(Z, Przez_PrT) + SPS_PrT(Przez_PrT, Do) + 2 * POI[3] # Oblicz czas PrT (2x dojscie do POI)

                    if POI[2] is not None:
                        Przez_PuT = Visum.Net.StopAreas.ItemByKey(POI[2]) # Przystanek dla POI (jesli jest)
                        CzPuT = SPS_PuT(Z, Przez_PuT) + SPS_PuT(Przez_PuT, Do)+ 2*POI[4]   # Oblicz czas PuT (2x dojscie do POI)
                    else:
                        CzPuT = 999999
                    print("From {} to {} Via {} in {} PrT, {} PuT".format(OZone[1], DZone[1], int(POI[0]), CzPrT, CzPuT))
                    df.loc[df.shape[0] + 1] = [OZone[1], DZone[1], nTrips, int(POI[0]), CzPrT, CzPuT] # zapisz rekord w bazie danych
    df.to_csv("data//POIs.csv")  # zapisz baze do pliku
    Visum.Graphic.StopDrawing = False

def Process():
    df1 = pd.read_csv('data//From_Via.csv')
    df2 = pd.read_csv('data//Via_To.csv')
    result = pd.merge(df1, df2, how='outer', on=['POI'])
    result['Czas_PrT']=result['Czas_PrT_x']+result['Czas_PrT_y']
    result['Czas_PuT'] = result['Czas_PuT_x'] + result['Czas_PuT_y']
    result = result[['Z_Rejon',"POI", "Do_Rejon",'Czas_PuT', 'Czas_PrT']] # u'Czas_PrT_x', u'Czas_PuT_x', u'Czas_PrT_y', u'Czas_PuT_y']]
    result.to_csv("data//From_Via_To.csv")  # zapisz baze do pliku




if __name__ == "__main__":

    Visum = win32com.client.Dispatch("Visum.Visum")  # uruchom Visum
    Visum.LoadVersion(VISUM_PATH)  # zaladuj plik
    POI2NearestZone(Visum)

    #POI2NearestNode(Visum) # przypisz wezly sieci do POI
    #POI2NearestSPoint(Visum) # przypisz przystanki do POI
    #MainLoopStages(Visum) # glowny algorytm
    #Process()
    Visum.SaveVersion(VISUM_PATH)








