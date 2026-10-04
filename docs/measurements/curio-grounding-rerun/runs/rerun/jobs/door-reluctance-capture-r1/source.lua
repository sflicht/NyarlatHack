return{name="Pallid Reed Sleeve",inspect=function(ctx)
local s,i,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if c==0 then return"The sleeve lies slack. Ivory, silk, and a reed that will not answer. Even the wrong high hush has gone thin."end
if t==0 then
if s>=50 then return"Clouded ivory clasps a silk sleeve. The reed within is mute, yet a high thread of air worries the seam, as if a call had stopped one breath short."end
return"The silk sleeve is too fine for your hands. Its mute reed ticks once against ivory, a high small sound with no mouth behind it."end
if t==1 then
if i==0 then return"One thread has left the seam. The ivory clasp is warm on one side only. Whatever note belongs here remains unsaid."end
return"A single thread stands off the silk. You nearly name the high interval it sketches, then the clasp cools and the name fails."end
if i>=200 then return"The omission is too precise to be wear. A high tone fails at the same place, and the clasp keeps a courtesy it was not given."end
if i>0 then return"You almost place the missing interval. The reed stays mute. The silk, however, has learned the shape of a high call it does not finish."end
return"The sleeve repeats its small fault: silk, then a high hush, then nothing. The repetition is neat, and that neatness is the wrong part."end,apply=function(ctx)
local s,i,c,t=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if c==0 then return{text="The sleeve gives nothing back. Ivory stays clouded, silk stays shut, and the high place in the air remains unfilled.",state=t,sanity_delta=0}end
local ns=t+1
if ns>255 then ns=255 end
if t==0 then
local d=-1
if s<40 then d=0 end
return{text="You turn the clasp. A high thread slips the seam and dies. The reed was never played; the silk remembers a pressure anyway.",state=ns,sanity_delta=d}end
if t==1 then return{text="The loose thread catches your nail. For a moment the sleeve holds a finished high note, then offers only the gap where it should be.",state=ns,sanity_delta=-1}end
if c==1 then
local d=-1
if s<30 then d=0 end
return{text="Little weight remains in the ivory. The high thread rises anyway, fails in its old place, and leaves the silk faintly proud.",state=ns,sanity_delta=d}end
if i>=500 then
if s<25 then return{text="The unnamed gap arrives and does not complete. At this thinness the failed high note is only silk moving, and then not.",state=ns,sanity_delta=0}end
local d=-1
if s>=80 then d=-2 end
return{text="The gap is familiar and still unnamed. A high courtesy fails on schedule. Precision does not steady you.",state=ns,sanity_delta=d}end
if t>=8 then
if s>=80 then return{text="The habit is no longer delicate. The high omission arrives already complete in its failure, and courtesy does not soften it.",state=ns,sanity_delta=-2}end
if s<40 then return{text="The missing note does not arrive. In its place is a small, exact quiet. Your breath matches it, and the sleeve asks nothing.",state=ns,sanity_delta=1}end
return{text="The silk has creased into a habit. Each handling finds the high omission already waiting, polite and unfinished.",state=ns,sanity_delta=-1}end
if s<40 then return{text="The missing note does not arrive. In its place is a small, exact quiet. Your breath matches it, and the sleeve asks nothing.",state=ns,sanity_delta=1}end
if i==0 then
local d=0
if s>=70 then d=-1 end
return{text="Again the hush arrives one beat late. You cannot say what it nearly was. The ivory is cool, and cooler along the crack.",state=ns,sanity_delta=d}end
if s>=75 then return{text="It happens again, too politely. Silk, high air, omission. You are not steadier for recognizing the order.",state=ns,sanity_delta=-2}end
return{text="The clasp turns a fraction and will not turn back. The same high fault repeats, stops, and leaves the reed exactly mute.",state=ns,sanity_delta=-1}end}