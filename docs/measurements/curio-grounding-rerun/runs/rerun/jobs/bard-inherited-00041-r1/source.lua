return{name='Pale Boxwood Peg',inspect=function(ctx)
local s,san=ctx.state,ctx.sanity
if s==0 then
if san>=70 then return 'A boxwood lute peg, pale and dry. One dark grain runs almost true, then hesitates.'
elseif san>=40 then return 'The peg is ordinary boxwood. Its dark grain seems to pause where the light thins.'
else return 'Boxwood, too pale. The grain stops short of the hole, as if it refused the turn.' end
elseif s==1 then
if ctx.insight>20 then return 'The same peg. The hesitation in the grain is a hair wider than the thumb remembers.'
else return 'You look again. The dark grain has a kink it did not earn from your hand.' end
elseif s<8 then
if ctx.charges==0 then return 'The peg lies still. The kink remains, counted once too often, and will not explain itself.'
elseif san<40 then return 'Each glance finds the grain one line short. You are not sure the shortage is in the wood.'
else return 'The kink holds. It resembles a rest more than a flaw, though no hand wrote it.' end
elseif san>=80 and ctx.insight<50 then return 'A pale peg. The grain is only wood. You repeat this, and the repetition does not settle.'
else return 'The boxwood is unchanged. What changes is how long you trust the first look.' end
end,apply=function(ctx)
local s,san,ins,ch=ctx.state,ctx.sanity,ctx.insight,ctx.charges
local text,ns,d
if s==0 then ns=1
if san>=60 then text='You turn the peg a fraction. The grain bends after the wood, late by a breath.'; d=-1
else text='The peg turns. The grain does not. For a moment the ear supplies a note you did not ask.'; d=-2 end
elseif s==1 then ns=2
if ins>100 then text='You turn it back. The kink remains, measured, not imagined. No string answers.'; d=0
elseif san<35 then text='Back again. The late grain follows, then stops, as if listening for a count.'; d=-2
else text='You ease it home. The hesitation stays in the grain, a rest with no bar around it.'; d=-1 end
elseif s<6 then ns=s+1
if ch<=1 then text='One last small turn. The kink neither deepens nor heals. Your ear insists on silence.'; d=0
elseif san>=75 then text='You turn it once more. Wood, only wood. Yet the grain arrives a moment after the twist.'; d=-1
else text='The peg answers your fingers late. You count the delay and lose the count by one.'; d=-1 end
else ns=s
if s<255 and san<50 and ins<=500 then ns=s+1 end
if ins>500 and san>=40 then text='The lateness is a fixed width, not a mood. Naming the width does not close it.'; d=0
elseif san>=80 then text='You set the peg down. The grain is a flaw. Saying so does not make the lateness leave.'; d=1
elseif san>=40 then text='Another turn changes nothing you can name. The hesitation keeps its own small time.'; d=0
else text='You stop turning. The grain seems to finish the motion without you, then does not.'; d=-2 end
end
return{text=text,state=ns,sanity_delta=d}
end}
