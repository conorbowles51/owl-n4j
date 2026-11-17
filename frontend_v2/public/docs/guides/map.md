# Map guide

## What the Map is for

The Map puts the case's places on one map: addresses found in the evidence, photos that carry a place in their own data, and positions read from the phones. It answers where things happened, what else sits near a place, and which phones were in an area and when.

***Main controls.*** The bar above the map holds **Layers**, **Confidence**, **Needs review**, **Proximity** and **Areas**, with the count of locations and phone positions at the right. **Zoom in**, **Zoom out** and **Fit all** sit at the top right of the map. **Legend** sits at the bottom left. **Phones** at the top left turns the phone positions on or off.

***When part of the map is hidden.*** While a filter or a drawn area is in use, a line under the bar reads "Showing N of M locations" and names what is narrowing it. **Clear** in that line brings every location back. While that line shows, the map is not the whole case.

## Read a place on the map

Point at a pin to see its details: its kind, name, coordinates, confidence, the address it was placed from, any manual corrections with who moved it and when, a short summary and its date. Click a pin to select it and open its full details in the side panel.

***When to use it.*** Use it to check where a place came from before relying on it.

***How to read it.*** The confidence badge says how sure the placement is. **Manual** means a person placed or moved it. **High**, **Medium** and **Low** come from the address lookup. **Unverified** means nothing has confirmed the position. "approximate" means the pin stands for an area, not an exact point. A pin placed by an address lookup says who asked for it and whether a person has confirmed it.

From the pin you can add it to a theory with **Theory…**, start a look with **Relate…** (the Corroborate guide explains looks), mark it significant, set it as the anchor for Proximity, or open it with **View in graph**.

## Choose what the map shows

**Legend** lists every kind of item on the map with its count, and every confidence level in use. Click a kind or a level to hide it; click it again to bring it back. **Filter…** at the top of the legend finds a kind by name. **Confidence** in the bar hides or shows each confidence level the same way, with the count beside each, and shows "Filtered" while any level is hidden. **Layers** turns on the **Heatmap**, which shows which parts of the map hold the most locations.

***When to use it.*** Hide the kinds that crowd the area of interest, or hide Low and Unverified pins to read only the placements that are sure.

## Check places that need review

**Needs review** lists the places whose position is in doubt: pins with low confidence, pins placed by an address lookup that no person has confirmed, and addresses that have no pin at all. The badge on the button counts them. Each row says why it is listed, for example "Not looked up yet" or "Looked up: no match found".

***What you can do.*** Click a row to select that place. **Look up** sends one address to the OpenStreetMap address service, which is outside this server. **Look up all N** says how many addresses it will send and how long it takes, then sends them one a second after you press **Send N**; **Stop** ends it part way. **Confirm** on a looked-up pin records that the pin is where the address is, and it then counts as placed by you.

***How to read the result.*** A pin found by a lookup reads "not confirmed" until a person confirms or moves it. The panel says whether this case looks addresses up automatically or only when someone clicks Look up; that choice lives in Case settings. People who can only view the case cannot look up or confirm.

## Find what is near a place

**Proximity** finds the locations within a distance of one place. Press **Proximity**, then click a pin, or use **Set as anchor** on a pin's details. A panel at the bottom right names the anchor, lets you set the radius from 0.1 km to 50 km, and lists every location inside it with its distance.

***When to use it.*** Use it to see which addresses, people or companies sit close to a scene or a known address.

***How to read the result.*** "No locations within N km" means no located item in the case falls inside that radius. It does not cover phone positions; draw an area for those.

## Draw an area

**Areas** opens the area filter. Choose **Box** or **Polygon**, then press **Draw area**. For a box, drag across the map. For a polygon, click each corner, then double-click or press the tick to finish; you can undo the last point or cancel. While drawing, drag with the right mouse button to move the map. Each shape waits under **Pending** until you press **Apply**, or **Discard** to drop it. You can draw several areas.

***When to use it.*** Draw round a scene, a street or a neighbourhood to see only what lies inside it.

***How to read the result.*** Once applied, the map shows only the case's locations inside the areas, and the yellow line counts them. With phone positions on, it also counts the phone positions inside the last area drawn. The bin beside an area removes it; **Clear areas** removes them all.

## Phones seen in an area

With phone positions on, drawing an area opens **Phones seen in this area**. It lists each phone with a position inside the last area drawn, how many positions it has there, and the first and last time it was there, in UTC. It also says how many of those positions have no time. Nothing in this list is capped.

***When to use it.*** Use it to answer which phones were at a place, and when.

***What you can do.*** **Conversations on this phone at that time** opens that phone's conversations for the same span, so the messages sent while it was there can be read next.

## Keep the places in an area

With an area applied, the area filter offers **Add N places to theory…**. It adds every place inside the areas to a theory as one group, with the areas themselves, so the reason the places belong together stays with them. Beside it, **Corroborate** saves the same places as one group and looks for how they could be linked. The Corroborate guide explains the result.

## Corroborate an area

This section applies only where the new Corroborate has been turned on for you.

***What it does.*** **Corroborate this area** in the area filter takes every phone position, photo and place inside the drawn areas into your Corroborate selection, then opens the question menu. The selection names what it holds, such as how many positions and places and from how many phones.

***When to use it.*** Use it to ask what links the phones and places seen in one location, for example who was at a scene on the nights of the incidents.

***How to read the result.*** "Nothing is inside the drawn area" means no phone position, photo or place falls inside it; draw a larger area or check the phones are on. The Corroborate guide explains the questions and the result.

## Photos on the map

A photo whose own data records where it was taken appears as a pin. Pointing at it shows the photo, its caption or file name, when it was taken, its altitude where recorded, and **Open the photo file**. In the legend, photo pins count under Document.

***How to read it.*** The place reads "Photo place. From the photo's data, not checked by a person." The badge reads Unverified. The place and date are what the camera or phone wrote into the file; a device's clock and position can be wrong, so treat them as a lead to check against other evidence. Photo pins count in drawn areas like any other place. The Evidence guide explains photo data and how to add a photo to the timeline.

## Phone positions

**Phones** at the top left shows or hides the positions read from the phones. At first it is on when the case has no other located items and off otherwise; after that the map keeps your choice for this case. The count at the right of the bar adds the phone positions.

The **Phone positions** panel at the bottom left reads "Showing N of M positioned records" and says how many records cannot be placed; **why** lists the reasons with counts. Those records are counted and never sent to a lookup service. Below that is every position in view with its phone, time, source and accuracy. The up and down arrows, or the arrow keys and J and K, step through the list and move the map to each one.

***What you can do with a position.*** **Open the record behind this** opens the phone record. **Show on Timeline** opens the timeline at that record. **Add to an address dossier** adds the position to a new or existing address dossier, with Undo.

***How to read it.*** Every position carries the words "Investigative location, not cell-site opinion". A position is a reading of what the phone recorded, not an expert's finding of where the handset was. "May come from another device" marks a position the phone may have received from a linked device.

## Narrow phone positions by phone and date

When the case has phones, a scope bar above the map narrows the phone positions to chosen phones and dates and counts the records with a position that remain. A scope carried from another phone screen applies its phones and dates here. People and kinds of record do not apply on the Map, and the bar names them under "Not applied on this screen". **Presets** offers ready scopes and your last scopes. **Carry this scope** opens the same scope in Conversations, the Graph or the Timeline.

## Show on Map from a phone record

**Show on Map** on a phone record opens the Map at that record's position. From a message that has no position of its own, the Map shows the same phone's positions within an hour of the message and says how many there are. Only those are drawn while the note shows; **Show every position** brings back the rest. When none fall within the hour, the note says how far in time the nearest one is, with **Show it**.

## Phone layers

This section applies only where phone layers have been turned on for you.

***What it does.*** A **Phones** row above the map lists every phone in the case with its own colour and shape, its label, its owner and its count of positions in view. Each phone has its own tick box. **Only this** leaves one phone on; **All** turns every phone back on. With more than 6 phones, the row offers **Find a phone or owner** and groups the phones by owner. The last phone that is on cannot be turned off. Your choice carries to the other phone screens and stays after a reload.

***When to use it.*** Use it to follow one phone, or to compare two or three phones without the rest.

***How to read it.*** "All N phones are on" means nothing is left out. "N of M phones are on" means the phones that are off are not drawn and not counted anywhere on the screen, including the area counts.

## Show routes

This section applies only where phone layers have been turned on for you.

***What it does.*** **Show routes** joins each phone's positions in time order in that phone's colour, with arrowheads pointing from the earlier position to the later one. Pointing at a leg states the phone, the two times and the two positions.

***When to use it.*** Use it to see the order in which a phone moved between places, and when.

***How to read the result.*** The line beside the box counts the moves drawn and the gaps over 2 hours that are not drawn, because a two-hour gap says nothing about the path between. Positions with no time are counted and left out of the routes. Above 20,000 timed positions the routes are thinned evenly, and the line says how many positions the routes use and how many are drawn; the dots themselves are not thinned.

## Where phones were together

This section applies only where both phone layers and phones together have been turned on for you.

***What it does.*** **Show where the phones were together** lists the times the phones that are on were in the same place, and marks each meeting on the map. Each meeting names the phones, the date and times in UTC, how many 15-minute time slots they shared in the same 550 m square, the best accuracy stated, and where the positions came from. A busy place is marked "Busy place: weak", because many people pass through it.

***When to use it.*** Use it to find when two or more people's phones met, as a lead to check against calls, messages and other evidence.

***What you can do.*** **Show** marks that meeting on the map. **Open the N records** lists the records behind it. **Corroborate** looks into how the meeting links to other items. It needs at least two phones on and at most 8; the panel says so otherwise. **What was searched** lists what was checked, so an empty list reads as nothing found in those records, not proof the phones never met.

## When the map cannot load

If the map cannot read the case's locations, the phones' positions or the places needing review, it says which part failed and offers **Try again**. When nothing at all could be read, it shows that message instead of an empty map. When one part fails, the map shows the rest and says that part is missing. "No location data" means the case holds nothing with a position yet; processing evidence that names places adds them.
