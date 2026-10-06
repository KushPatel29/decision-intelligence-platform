"""Author an offline native Power BI project from the delivered import contracts.

The Microsoft modeling connector loads and exports this BIM as TMDL separately.
Report JSON is checked against Microsoft's published PBIR schemas.
"""
from pathlib import Path
import json
import pandas as pd
from decision_platform.config import ROOT

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2),encoding="utf-8")

def main():
    target=ROOT/"powerbi"/"Corridor";tables=[]
    bi=ROOT/"outputs/powerbi"
    for name in ["loyalty_ledger","zone_hour_forecast","price_allocation","experiment_subgroups"]:
        pd.read_csv(ROOT/"outputs"/(name+".csv")).to_csv(bi/(name+".csv"),index=False)
    registry=json.loads((ROOT/"outputs/model_registry.json").read_text())
    pd.DataFrame(registry).to_csv(bi/"model_registry.csv",index=False)
    quality=json.loads((ROOT/"outputs/quality_gate.json").read_text())
    pd.DataFrame(quality["checks"]).to_csv(bi/"quality_gate.csv",index=False)
    names=["customer_360","decision_table","zone_capacity","monthly_performance","pricing_scenarios","dim_zone","dim_offer","model_metrics","feature_drift","experiment_results","loyalty_ledger","zone_hour_forecast","price_allocation","experiment_subgroups","model_registry","quality_gate"]
    for name in names:
        frame=pd.read_csv(ROOT/"outputs"/"powerbi"/(name+".csv"))
        columns=[];mtypes=[]
        for field in frame:
            dtype=frame[field].dtype
            if pd.api.types.is_bool_dtype(dtype):dt,mt="boolean","type logical"
            elif pd.api.types.is_integer_dtype(dtype):dt,mt="int64","Int64.Type"
            elif pd.api.types.is_float_dtype(dtype):dt,mt="double","type number"
            else:dt,mt="string","type text"
            columns.append({"name":field,"dataType":dt,"sourceColumn":field,"summarizeBy":"none"})
            mtypes.append('{"'+field+'", '+mt+'}')
        file=str(ROOT/"outputs"/"powerbi"/(name+".csv")).replace('\\','/')
        expression=['let',f'    Source = Csv.Document(File.Contents("{file}"),[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),','    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),','    Typed = Table.TransformColumnTypes(Headers, {'+', '.join(mtypes)+'}, "en-CA")','in','    Typed']
        tables.append({"name":name,"columns":columns,"partitions":[{"name":name,"mode":"import","source":{"type":"m","expression":expression}}]})
    measures={
        "Selected contacts":("DISTINCTCOUNT(decision_table[customer_id])","#,0"),
        "Expected additional trips":("SUM(decision_table[incremental_trips])","#,0.0"),
        "Expected incentive costs":("SUM(decision_table[cost])","$#,0.00"),
        "Expected net contribution":("SUM(decision_table[net_contribution])","$#,0.00"),
        "Net ROI":("DIVIDE([Expected net contribution], [Expected incentive costs])","0.0%"),
        "Points awarded":("SUM(decision_table[points])","#,0"),
        "Customers":("COUNTROWS(customer_360)","#,0"),
        "Average projected value":("AVERAGE(customer_360[clv_12m])","$#,0.00"),
        "Trips":("SUM(monthly_performance[trips])","#,0"),
        "Revenue":("SUM(monthly_performance[revenue])","$#,0"),
        "Utilization":("DIVIDE(SUM(zone_capacity[baseline_forecast])+SUM(zone_capacity[allocated_trips]),SUM(zone_capacity[capacity_trips]))","0.0%"),
        "Remaining headroom":("SUM(zone_capacity[remaining_with_reserve])","#,0.0"),
        "Mean price demand index":("AVERAGE(pricing_scenarios[demand_index])","0.0"),
        "Mean response lift":("AVERAGE(experiment_results[difference])","0.0%"),
        "Test AUC":("AVERAGE(model_metrics[roc_auc])","0.000"),
        "Mean price revenue index":("AVERAGE(pricing_scenarios[revenue_index])","0.0"),
        "Loyalty additional trips":('CALCULATE([Expected additional trips], decision_table[offer_id] = "loyalty_500")',"#,0.0"),
        "Mean test Brier":("AVERAGE(model_metrics[brier])","0.000"),
        "High inactivity risk":('COUNTROWS(FILTER(customer_360, customer_360[churn_probability] > 0.5))',"#,0"),
        "Digital engagements":("SUM(customer_360[digital_events_30d])","#,0"),
        "Points redeemed":("SUM(loyalty_ledger[points_redeemed])","#,0"),
        "Points balance":("SUM(loyalty_ledger[points_balance])","#,0"),
        "Hourly forecast trips":("SUM(zone_hour_forecast[forecast_trips])","#,0.0"),
        "Price contribution change":("SUM(price_allocation[incremental_contribution])","$#,0.00"),
        "Consumer surplus change":("SUM(price_allocation[consumer_surplus_change])","$#,0.00"),
        "Effect interval lower":("AVERAGE(experiment_results[ci_low])","0.0%"),
        "Effect interval upper":("AVERAGE(experiment_results[ci_high])","0.0%"),
        "Minimum adjusted p":("MIN(experiment_results[p_adjusted])","0.0000"),
        "Mean feature PSI":("AVERAGE(feature_drift[psi])","0.000"),
        "Registered models":("COUNTROWS(model_registry)","#,0"),
        "Model acceptance passes":('COUNTROWS(FILTER(quality_gate, quality_gate[passed] = TRUE()))',"#,0"),
        "Candidate version":("MAX(model_registry[version])","#,0"),
    }
    tables[1]["measures"]=[{"name":name,"expression":expr,"formatString":fmt,"description":"Synthetic portfolio result. Forecasts do not represent measured business impact."} for name,(expr,fmt) in measures.items()]
    relationships=[]
    for source,field,dim,key in [("decision_table","customer_id","customer_360","customer_id"),("customer_360","home_zone","dim_zone","zone_id"),("zone_capacity","zone_id","dim_zone","zone_id"),("pricing_scenarios","zone_id","dim_zone","zone_id"),("decision_table","offer_id","dim_offer","offer_id")]:
        relationships.append({"name":source+"_"+field,"fromTable":source,"fromColumn":field,"toTable":dim,"toColumn":key,"crossFilteringBehavior":"oneDirection"})
    save(target/"Corridor.SemanticModel"/"model.bim",{"name":"Corridor","compatibilityLevel":1600,"model":{"culture":"en-CA","defaultPowerBIDataSourceVersion":"powerBI_V3","tables":tables,"relationships":relationships}})
    save(target/"Corridor.SemanticModel"/"definition.pbism",{"version":"4.0","settings":{}})
    save(target/"Corridor.pbip",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json","version":"1.0","artifacts":[{"report":{"path":"Corridor.Report"}}],"settings":{"enableAutoRecovery":True}})
    save(target/"Corridor.Report"/"definition.pbir",{"$schema":"https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json","version":"4.0","datasetReference":{"byPath":{"path":"../Corridor.SemanticModel"}}})
    base="https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    save(target/"Corridor.Report"/"definition"/"version.json",{"$schema":base+"versionMetadata/1.0.0/schema.json","version":"2.0.0"})
    theme_name="CorridorNightSignal"
    save(target/"Corridor.Report"/"StaticResources"/"RegisteredResources"/(theme_name+".json"),json.loads((ROOT/"powerbi/corridor_theme.json").read_text()))
    save(target/"Corridor.Report"/"definition"/"report.json",{"$schema":base+"report/3.0.0/schema.json","themeCollection":{"baseTheme":{"name":"CY24SU11","reportVersionAtImport":{"visual":"1.8.0","report":"2.0.0","page":"1.3.0"},"type":"SharedResources"},"customTheme":{"name":theme_name,"reportVersionAtImport":{"visual":"1.8.0","report":"2.0.0","page":"1.3.0"},"type":"RegisteredResources"}},"resourcePackages":[{"name":"RegisteredResources","type":"RegisteredResources","items":[{"name":theme_name,"path":theme_name+".json","type":"CustomTheme"}]}]})
    specs=[("Executive overview",[("Expected additional trips",None),("Expected net contribution",None),("Expected incentive costs",None),("Selected contacts",None),("Trips",("monthly_performance","month")),("Revenue",("monthly_performance","month"))]),
        ("Customer intelligence",[("Customers",None),("Average projected value",None),("High inactivity risk",None),("Digital engagements",None),("Customers",("customer_360","rfm_segment")),("Average projected value",("customer_360","rfm_segment")),("High inactivity risk",("customer_360","rfm_segment")),("Digital engagements",("customer_360","rfm_segment"))]),
        ("Pricing",[("Mean price demand index",None),("Mean price revenue index",None),("Price contribution change",None),("Consumer surplus change",None),("Mean price demand index",("pricing_scenarios","price_change")),("Mean price revenue index",("pricing_scenarios","price_change")),("Price contribution change",("price_allocation","period")),("Consumer surplus change",("price_allocation","period"))]),
        ("Promotions & rewards",[("Selected contacts",None),("Expected net contribution",None),("Expected incentive costs",None),("Net ROI",None),("Expected net contribution",("dim_offer","offer_name")),("Expected incentive costs",("dim_offer","offer_name"))]),
        ("Loyalty",[("Points awarded",None),("Loyalty additional trips",None),("Points redeemed",None),("Points balance",None),("Points awarded",("dim_zone","zone_name")),("Loyalty additional trips",("dim_zone","zone_name"))]),
        ("Transportation",[("Utilization",None),("Remaining headroom",None),("Utilization",("dim_zone","zone_name")),("Remaining headroom",("zone_capacity","period")),("Hourly forecast trips",("zone_hour_forecast","hour")),("Hourly forecast trips",("zone_hour_forecast","direction"))]),
        ("Experiments",[("Mean response lift",None),("Minimum adjusted p",None),("Mean response lift",("experiment_results","arm")),("Effect interval lower",("experiment_results","arm")),("Effect interval upper",("experiment_results","arm"))]),
        ("Model monitoring",[("Test AUC",None),("Mean test Brier",None),("Registered models",None),("Model acceptance passes",None),("Test AUC",("model_metrics","model")),("Mean test Brier",("model_metrics","model")),("Mean feature PSI",("feature_drift","feature")),("Candidate version",("model_registry","model"))])]
    ids=[]
    for index,(title,visuals) in enumerate(specs):
        page=f"page_{index+1:02}";ids.append(page);folder=target/"Corridor.Report"/"definition"/"pages"/page
        save(folder/"page.json",{"$schema":base+"page/2.0.0/schema.json","name":page,"displayName":title,"displayOption":"FitToPage","height":1100 if sum(c is not None for _,c in visuals)>2 else 720,"width":1280})
        chart_number=0
        for number,(measure,category) in enumerate(visuals):
            vid=f"visual_{number+1:02}"
            projection={"field":{"Measure":{"Expression":{"SourceRef":{"Entity":"decision_table"}},"Property":measure}},"queryRef":"decision_table."+measure,"nativeQueryRef":measure}
            query={"Values":{"projections":[projection]}} if category is None else {"Y":{"projections":[projection]},"Category":{"projections":[{"field":{"Column":{"Expression":{"SourceRef":{"Entity":category[0]}},"Property":category[1]}},"queryRef":".".join(category),"nativeQueryRef":category[1]}]}}
            position={"x":30+number*305 if category is None else 30+((chart_number%2)*625),"y":30 if category is None else 210+(chart_number//2)*420,"z":number,"height":140 if category is None else 380,"width":285 if category is None else 590,"tabOrder":number}
            if category is not None:chart_number+=1
            visual={"visualType":"card" if category is None else "clusteredColumnChart","query":{"queryState":query},"drillFilterOtherVisuals":True,
                "visualContainerObjects":{"title":[{"properties":{"show":{"expr":{"Literal":{"Value":"true"}}},"text":{"expr":{"Literal":{"Value":"'"+measure+"'"}}}}}]}}
            save(folder/"visuals"/vid/"visual.json",{"$schema":base+"visualContainer/2.1.0/schema.json","name":vid,"position":position,"visual":visual})
    save(target/"Corridor.Report"/"definition"/"pages"/"pages.json",{"$schema":base+"pagesMetadata/1.0.0/schema.json","pageOrder":ids,"activePageName":ids[0]})
    print(f"Native project authored: {len(tables)} import tables, {len(measures)} measures, {len(specs)} pages")

if __name__=="__main__":main()
