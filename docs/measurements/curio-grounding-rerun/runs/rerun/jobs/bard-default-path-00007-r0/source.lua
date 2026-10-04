return{name="the short fourth",inspect=function(ctx)
local s,i,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if s<50 then
if t>0 then return"Counted before, the missing line feels longer than the horn meant to hold it."end
return"The unfinished line seems to run past the horn. Fingers stop. The rest is not in the hand."
end
if i>=500 then
if t>0 then return"The stricter measure still closes it. What stays short is the flatness you prefer."end
return"In a stricter measure the square already closes. The shortage is the angle of regard."
end
if i>0 then
if t>0 then return"Turned already, thickness still accounts for the gap. The square holds. The angle of view does not."end
return"The wafer has a thickness the flat look missed. The gap may be that edge, seen too level."
end
if c==0 then
if t>0 then return"Done with turning. The count stands. The short edge has not lengthened."end
return"Cool horn, done with turning. The fourth edge remains short. The plane asks nothing."
end
if c==1 then
if t>0 then return"Near stillness. The short edge has not lengthened. Only the count of the gap moved."end
return"A thin horn square, nearly done with handling. Three edges meet. The fourth is a hair short."
end
if t>0 then return"The horn square again. The short edge has not lengthened. Only the count has moved."end
return"A thin horn square, pocket-warm. Three edges meet. The fourth stops a bright hair short."
end,apply=function(ctx)
local s,i,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local n=t
if n<255 then n=n+1 end
if c==0 then return{text="The touch returns nothing new. The fourth edge is short. That is the whole fact.",state=t,sanity_delta=0}end
if s<50 then
if t>=3 then return{text="Counted past the square's own sides, the extra length is a mistake of measure, and it unsettles.",state=n,sanity_delta=-2}end
return{text="You press the short edge flat. It will not seat. The continuing line is not a place the hand can enter.",state=n,sanity_delta=-1}
end
if i>=500 then
if t>0 then return{text="Still closed under the stricter angle. Setting it down again changes neither horn nor look.",state=n,sanity_delta=0}end
return{text="A stricter angle already closes the figure. The discrepancy stays with the look, not the horn.",state=n,sanity_delta=0}
end
if i>0 then
if t>0 then return{text="Tilted as before, thickness still explains the gap. Repeating the proof adds no steadiness.",state=n,sanity_delta=0}end
return{text="You tilt the wafer. The short edge reads as thickness, not absence. The level gaze, not the horn, was short.",state=n,sanity_delta=1}
end
if c==1 then
if t>0 then
if s>=80 then return{text="The palm is steady, patience thin. The gap stays one hair. Three edges true. No note is owed.",state=n,sanity_delta=0}end
return{text="Little patience left. The gap stays one hair. Three edges remain true, and the note is absent.",state=n,sanity_delta=-1}
end
return{text="Little patience remains. Even so the fourth edge stops short, and the horn keeps no closing tone.",state=n,sanity_delta=-1}
end
if t==0 then return{text="You lay the wafer flat. The fourth edge stops short. The ear expects a tone the horn does not hold.",state=n,sanity_delta=-1}end
if s>=80 then return{text="You count the hair of light again. It matches. The square withholds the note and keeps its measure.",state=n,sanity_delta=0}end
return{text="The gap is the same hair. Repeating the measure makes the missing close feel nearer than the horn.",state=n,sanity_delta=-1}
end}