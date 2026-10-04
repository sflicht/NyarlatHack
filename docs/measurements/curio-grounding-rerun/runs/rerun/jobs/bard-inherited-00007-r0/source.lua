return{name="Compliment Reed",inspect=function(ctx)
local st,s,n,c=ctx.state,ctx.sanity,ctx.insight,ctx.charges
if c==0 then return"Only lacquer remains, and it still looks ready. Readiness, unasked, is a small insolence."end
if st>=2 then if n>0 then return"The gloss repeats one improved mouth. You can count the places where yours was revised."end
return"The same sweetness sits in the lacquer. It has not learned you. It does not need to."end
if st==1 then if s<50 then return"A kinder outline of your lip remains in the black. Kindness this exact is not comfort."end
return"The reed keeps yesterday's compliment. Polished things are loyal only to their own finish."end
if c==1 then return"One unused shine. The reed looks more eager for that scarcity than a mouth should allow."end
if n>500 then return"The lacquer is only lacquer. What it improves is the idea of a mouth, not the air."end
if n>0 then return"Too fine a reed for any breath. The gloss edits the lip before the lip arrives."end
if s>=90 then return"Black lacquer, thinner than breath. Near the lip it proposes a tone you have not earned."end
if s>=50 then return"A slender reed of black lacquer. Its gloss flatters the mouth that has not yet touched it."end
return"The reed's shine is steadier than your mouth. It offers that steadiness as if it were style."end,apply=function(ctx)
local st,s,n,c=ctx.state,ctx.sanity,ctx.insight,ctx.charges
if c==0 then return{text="The lacquer declines the mouth. No shine remains to lend, and the refusal is beautifully made.",state=st,sanity_delta=0}end
local nxt=st+1
if nxt>255 then nxt=255 end
if st>=2 then
if s<=1 then if n>0 then return{text="The revision returns, and finds almost nothing left to improve. Precision, here, is only rude.",state=nxt,sanity_delta=0}end
return{text="The improved silence comes again. There is little composure left for it to revise.",state=nxt,sanity_delta=0}end
if n>0 then return{text="Again the correction, exact to the last shine. The pose remains; the sweetness does not.",state=nxt,sanity_delta=-2}end
return{text="Again the same improved silence. You hear how little of the sweetness was yours.",state=nxt,sanity_delta=-1}end
if st==1 then
if c==1 then return{text="One shine left, spent on making the last pose look chosen. It was only lacquer.",state=nxt,sanity_delta=-1}end
return{text="It repeats the sweetness exactly. Exactness, in a compliment, is already cold.",state=nxt,sanity_delta=-1}end
if s<40 then return{text="The gloss lends you a steadier mouth. You take the kindness, knowing the finish is not yours.",state=nxt,sanity_delta=1}end
if n>0 then return{text="Set to the lip, the lacquer corrects you by a shade. The improvement is not a gift.",state=nxt,sanity_delta=-1}end
if s>=90 then return{text="You try the pose. The air returns sweeter, and a fraction off your own key.",state=nxt,sanity_delta=-1}end
return{text="The reed flatters a note it will not sound. You accept the finish, and feel the cost.",state=nxt,sanity_delta=-1}end}
