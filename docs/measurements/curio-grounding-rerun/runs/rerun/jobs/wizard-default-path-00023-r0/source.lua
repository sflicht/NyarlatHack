return {
name='Damp Assurance Slip',
inspect=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if c==0 then
return 'Thumb-worn blank. A firm total once occupied this slip; only the dent of certainty remains.'
elseif st==0 and i==0 and s>=80 then
return 'Neat ink declares the count settled. One corner is damp, and the damp does not concur.'
elseif st==0 and i==0 then
return 'The totals are neat and uneven. Certainty is in the hand; the damp corner withholds its vote.'
elseif st==0 and i<100 then
return 'Two totals share the line. The darker digit looks official; the paler one looks earlier.'
elseif st==0 then
return 'The later total sits over a smaller one. Assurance arrived before any recount could.'
elseif st<4 and s>=80 and i<20 then
return 'You favor the darker figure. The pale twin reads, conveniently, as a blot from the damp.'
elseif st<4 and s<40 then
return 'The totals trade rank as you look. Whichever you grant, the wet corner has already refused.'
elseif st<4 then
return 'The hand is sure. The fiber under the ink is soft, worked past the point of proof.'
elseif i>500 then
return 'Corrections cancel. What remains is the habit of totaling before the count was finished.'
elseif c==1 then
return 'One reading left in the ink. It still offers agreement, and still only one hand made it.'
elseif s<35 then
return 'The firm number looks loud for such thin paper. You do not let it finish its claim.'
else
return 'A single firm number, and beside it a fainter twin waiting to be called a shadow.'
end
end,
apply=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local nst=st+1
if nst>255 then nst=255 end
local d,t=0,''
if c==0 then
nst=st
t='Nothing takes the pressure. The slip stays blank, and the count of it does not change.'
elseif st==0 and i==0 and s>=80 then
d=-1
t='You grant the darker total. It feels agreed, then merely written, and a little steadiness goes.'
elseif st==0 and i==0 then
t='You sound the darker total and do not grant it. The damp corner keeps its own small counsel.'
elseif st==0 then
t='You set the two figures side by side. Neither yields, and the paper stays only paper.'
elseif s<35 then
d=1
t='You decline every total. The argument loosens, and the damp disagreement is easier to hold.'
elseif i>400 and s>=50 then
t='You read the overwriting as haste, not verdict. The certainty does not enter you.'
elseif c==1 and s>=80 and i<40 then
d=-2
t='The last digit smears, and you prefer it still. Slight paper, heavy grant: more steadiness goes.'
elseif c==1 then
d=-1
t='The last dark digit smears under your thumb. Agreement becomes a stain, not a sum.'
elseif s>=90 and i<20 then
d=-1
t='You grant it again. The stroke is sure, and surer than the damp proof beneath it.'
elseif s>=60 and i<100 then
d=-1
t='The firmer number almost convinces. The damp edge darkens, and the trust does not quite hold.'
else
d=1
t='You leave the totals unmatched. Modest ink, refused, returns a little calm to the hand.'
end
return {text=t,state=nst,sanity_delta=d}
end
}
