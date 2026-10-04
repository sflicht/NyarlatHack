local function inspect(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if st==0 then
  if c==0 then return 'The hem is limp. No stitch lifts. If a count remains, it is finished.'
  elseif s<50 then return 'The hem will not hold a count. Six, then seven, then a gap.'
  elseif i==0 and s>=90 then return 'Stiff linen, hemmed in seven short stitches. Plain, if you do not linger.'
  elseif i>0 then return 'Seven stitches, spaced like rests in a tune not sounded. Only linen.'
  else return 'A thumb-creased linen card. Seven stitches hem the edge. Resin in the cloth.'
  end
elseif st<4 then
  if s<50 then return 'The hem will not match itself. Each count ends on a different stitch.'
  elseif st==1 then return 'You counted seven. The seventh stitch is shorter now, as if the thread crept.'
  elseif st==2 and i>100 then return 'The gaps are a pattern now, or you made them one. The card will not say.'
  elseif st==2 then return 'From the other end the hem shows eight. The extra may be a crease-shadow.'
  else return 'The long stitch has moved one place. You did not turn the card.'
  end
elseif st<12 then
  if c==0 then return 'The stitches lie flat. The card offers no further correction.'
  elseif s<40 then return 'Each look moves a stitch. You are not sure the moving is in the thread.'
  elseif st<8 then return 'The fourth gap is wider than the third. It was not, a moment ago.'
  else return 'The wide gap has shifted toward the end. You can point to it, not keep it.'
  end
elseif i>500 and s>=50 then return 'The hem repeats a figure you almost name, then refuses it. Seven, or a rest.'
elseif s<40 then return 'The stitches crawl if you hold the count. Look away: only thread again.'
else return 'Only linen and thread. The count will not stay where you leave it.'
end
end
local function apply(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local ns,d,t=st,0,''
if c==0 then
  t='The hem does not lift. The stitches stay where the last count left them.'
elseif st==0 then
  ns=1
  if s>=80 then d=-1; t='You count seven. The seventh stitch shortens under your thumb. You did not pull it.'
  elseif s<40 then d=-1; t='The count slips as you press. Six, then a gap. Your hand is steady. The thread is not.'
  else t='Pressed flat, a faint resin scent. Seven stitches. One sits a hair higher.'
  end
elseif st<5 then
  ns=st+1
  if i==0 then t='You count back from the end. Eight stitches, or the first was a crease-shadow.'
  elseif i>200 then d=-1; t='The gaps suggest a phrase, then withdraw it. Naming them does not make them agree.'
  else t='A second reading moves the long stitch one place left. The card was not turned.'
  end
elseif st<15 then
  ns=st+1
  if s<30 then d=1; t='You stop counting. The hem goes almost even. The relief is small and unexplained.'
  elseif c==1 then t='On this last press the stitches lie still. The wrong gap does not widen.'
  else d=-1; t='The pattern answers the looking: one stitch more, where your thumb already was.'
  end
else
  if st<255 then ns=st+1 end
  if s>=50 then t='The hem repeats. You can leave the count wrong. The linen allows it.'
  else d=1; t='You set the card down mid-count. The unease thins by a degree, no more.'
  end
end
return {text=t,state=ns,sanity_delta=d}
end
return {name='Hemmed Pitch-Card',inspect=inspect,apply=apply}
