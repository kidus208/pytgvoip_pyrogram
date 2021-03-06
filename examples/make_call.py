from tgvoip import VoIPServerConfig
from tgvoip_pyrogram import VoIPFileStreamService, VoIPNativeIOService
import pyrogram


VoIPServerConfig.set_bitrate_config(80000, 100000, 60000, 5000, 5000)
client = pyrogram.Client('session')
client.start()

voip_service = VoIPFileStreamService(client, receive_calls=False)  # use VoIPNativeIOService for native I/O
call = voip_service.start_call('@bakatrouble')
call.play('input.raw')
call.play_on_hold(['input.raw'])
call.set_output_file('output.raw')


@call.on_call_state_changed
def state_changed(call, state):
    print('State changed:', call, state)


# you can use `call.on_call_ended(lambda _: app.stop())` here instead
@call.on_call_ended
def call_ended(call):
    client.stop()
